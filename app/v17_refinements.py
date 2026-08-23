from __future__ import annotations

import json
from typing import Any

from nicegui import ui

from . import ui as ui_module
from . import v13, v15, v15_refinements, v16, v16_refinements, v17
from .excel_repository import ExcelRepository
from .ui_context import ensure_scoped_ui


RESOURCE_ORDER_FIELD = "Ordre"
SORT_AVAIL_DESC = "availability_desc"
SORT_AVAIL_ASC = "availability_asc"
SORT_ALPHA_ASC = "alpha_asc"
SORT_ALPHA_DESC = "alpha_desc"
SORT_MANUAL = "manual"
SORT_OPTIONS = {
    SORT_AVAIL_DESC: "Disponibilité — plus disponible d'abord",
    SORT_AVAIL_ASC: "Disponibilité — plus occupé d'abord",
    SORT_ALPHA_ASC: "Alphabétique A → Z",
    SORT_ALPHA_DESC: "Alphabétique Z → A",
    SORT_MANUAL: "Ordre manuel",
}


_SCROLL_SETUP_JS = r"""
(() => {
  const PAGE_KEY = 'planner:v17:planning:windowY';
  const GRID_KEY = 'planner:v17:planning:gridScroll';
  const PENDING_KEY = 'planner:v17:planning:pendingCollapsed';

  const install = () => {
    // Preserve the browser/page vertical position across NiceGUI refreshes.
    const savedWindowY = Number(sessionStorage.getItem(PAGE_KEY) || 0);
    if (savedWindowY > 0) window.scrollTo({top: savedWindowY, behavior: 'instant'});
    if (!window.__plannerV17WindowScrollInstalled) {
      window.addEventListener('scroll', () => {
        sessionStorage.setItem(PAGE_KEY, String(window.scrollY || 0));
      }, {passive: true});
      window.__plannerV17WindowScrollInstalled = true;
    }

    // Preserve both axes of the large operational planning scroll area.
    const scrollRoot = [...document.querySelectorAll('.q-scrollarea')]
      .find(el => el.querySelector('.schedule-grid'));
    const scrollContainer = scrollRoot?.querySelector('.q-scrollarea__container');
    if (scrollContainer) {
      let saved = {};
      try { saved = JSON.parse(sessionStorage.getItem(GRID_KEY) || '{}'); } catch (_) {}
      if (Number.isFinite(Number(saved.top))) scrollContainer.scrollTop = Number(saved.top);
      if (Number.isFinite(Number(saved.left))) scrollContainer.scrollLeft = Number(saved.left);
      if (!scrollContainer.dataset.v17ScrollTracking) {
        scrollContainer.dataset.v17ScrollTracking = '1';
        scrollContainer.addEventListener('scroll', () => {
          sessionStorage.setItem(GRID_KEY, JSON.stringify({
            top: scrollContainer.scrollTop || 0,
            left: scrollContainer.scrollLeft || 0,
          }));
        }, {passive: true});
      }
    }

    // Make the pending-approval section collapsible without changing its business logic.
    const cards = [...document.querySelectorAll('.q-card')];
    const pendingCard = cards.find(card =>
      (card.textContent || '').includes("En attente d'approbation dans cette semaine")
    );
    if (pendingCard && !pendingCard.dataset.v17Collapsible) {
      pendingCard.dataset.v17Collapsible = '1';
      const directChildren = [...pendingCard.children];
      const titleHost = directChildren.find(child =>
        (child.textContent || '').includes("En attente d'approbation dans cette semaine")
      ) || directChildren[0];

      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'v17-pending-toggle';
      button.style.cssText = [
        'align-self:flex-start',
        'border:1px solid #cbd5e1',
        'border-radius:6px',
        'padding:4px 10px',
        'font-size:12px',
        'background:white',
        'cursor:pointer',
        'margin-left:auto'
      ].join(';');
      pendingCard.insertBefore(button, pendingCard.children[1] || null);

      const apply = collapsed => {
        directChildren.forEach(child => {
          if (child !== titleHost) child.style.display = collapsed ? 'none' : '';
        });
        button.textContent = collapsed ? 'Afficher' : 'Réduire';
        button.title = collapsed
          ? "Afficher les demandes en attente d'approbation"
          : "Réduire les demandes en attente d'approbation";
        pendingCard.style.paddingBottom = collapsed ? '10px' : '';
        sessionStorage.setItem(PENDING_KEY, collapsed ? '1' : '0');
      };

      let collapsed = sessionStorage.getItem(PENDING_KEY) === '1';
      apply(collapsed);
      button.addEventListener('click', event => {
        event.preventDefault();
        event.stopPropagation();
        collapsed = !collapsed;
        apply(collapsed);
      });
    }
  };

  // NiceGUI/Quasar can finish laying out a moment after the Python render returns.
  requestAnimationFrame(() => requestAnimationFrame(install));
  setTimeout(install, 120);
})();
"""


def _ensure_manual_order_column(repo: ExcelRepository) -> None:
    if RESOURCE_ORDER_FIELD not in v16_refinements.RESOURCE_PROFILE_HEADERS:
        v16_refinements.RESOURCE_PROFILE_HEADERS.append(RESOURCE_ORDER_FIELD)
    v16_refinements.ensure_resource_profiles(repo)


def _order_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _resource_order_map(repo: ExcelRepository) -> dict[str, float]:
    _ensure_manual_order_column(repo)
    result: dict[str, float] = {}
    for row in v16_refinements._profile_records(repo):
        name = str(row.get("Technicien") or "").strip()
        order = _order_number(row.get(RESOURCE_ORDER_FIELD))
        if name and order is not None:
            result[name] = order
    return result


def _update_resource_profile_extended(
    repo: ExcelRepository,
    technician: str,
    resource_class: str | None,
    competencies: Any,
    note: str = "",
    order: Any = None,
) -> None:
    _ensure_manual_order_column(repo)
    name = str(technician or "").strip()
    if not name:
        raise ValueError("Le technicien est requis.")

    chosen_class = v16._normalize_resource_class(resource_class)
    if resource_class and not chosen_class:
        raise ValueError("La classe sélectionnée n'est pas reconnue.")

    rows = v16_refinements._profile_records(repo)
    target = next(
        (row for row in rows if str(row.get("Technicien") or "").strip() == name),
        None,
    )
    chosen_order = _order_number(order)
    if target is not None and order is None:
        chosen_order = _order_number(target.get(RESOURCE_ORDER_FIELD))

    payload = {
        "Technicien": name,
        "Classe": chosen_class,
        "Competences": v16_refinements._join_competencies(competencies),
        "Note": str(note or "").strip() or None,
        RESOURCE_ORDER_FIELD: chosen_order,
    }

    if target is None:
        repo._append_dict_row(
            v16_refinements.RESOURCE_PROFILE_SHEET,
            v16_refinements.RESOURCE_PROFILE_HEADERS,
            payload,
            v16_refinements.RESOURCE_PROFILE_TABLE,
        )
        repo.save()
        return

    excel_row = int(target["_row"])
    with repo._lock:
        sheet = repo._book().sheets[v16_refinements.RESOURCE_PROFILE_SHEET]
        sheet.range(
            (excel_row, 1),
            (excel_row, len(v16_refinements.RESOURCE_PROFILE_HEADERS)),
        ).value = [[payload.get(header) for header in v16_refinements.RESOURCE_PROFILE_HEADERS]]
        repo.save()


def _resource_sort_script(self: ui_module.PlannerUI) -> str:
    mode = str(getattr(self, "planning_resource_sort", SORT_AVAIL_DESC) or SORT_AVAIL_DESC)
    orders = _resource_order_map(self.repo)
    stats = v16._weekly_resource_stats(self.repo, self.current_week)
    free = {
        str(name): float(values.get("prudent_free", 0.0) or 0.0)
        for name, values in stats.items()
    }
    all_names = sorted(set(free) | set(orders), key=len, reverse=True)

    mode_json = json.dumps(mode, ensure_ascii=False)
    orders_json = json.dumps(orders, ensure_ascii=False)
    free_json = json.dumps(free, ensure_ascii=False)
    names_json = json.dumps(all_names, ensure_ascii=False)

    return f"""
(() => {{
  const mode = {mode_json};
  const orders = {orders_json};
  const free = {free_json};
  const knownNames = {names_json};

  const resourceName = cell => {{
    const text = (cell?.textContent || '').trim();
    return knownNames.find(name => text.startsWith(name)) || text.split('\n')[0].trim();
  }};

  const compareNames = (a, b) => a.localeCompare(b, 'fr', {{sensitivity: 'base'}});
  const compareRows = (a, b) => {{
    const nameA = resourceName(a[0]);
    const nameB = resourceName(b[0]);
    if (mode === 'alpha_asc') return compareNames(nameA, nameB);
    if (mode === 'alpha_desc') return compareNames(nameB, nameA);
    if (mode === 'availability_asc') {{
      const diff = Number(free[nameA] || 0) - Number(free[nameB] || 0);
      return diff || compareNames(nameA, nameB);
    }}
    if (mode === 'manual') {{
      const orderA = Number.isFinite(Number(orders[nameA])) ? Number(orders[nameA]) : 999999;
      const orderB = Number.isFinite(Number(orders[nameB])) ? Number(orders[nameB]) : 999999;
      return (orderA - orderB) || compareNames(nameA, nameB);
    }}
    const diff = Number(free[nameB] || 0) - Number(free[nameA] || 0);
    return diff || compareNames(nameA, nameB);
  }};

  const apply = () => {{
    document.querySelectorAll('.schedule-grid').forEach(grid => {{
      const children = [...grid.children];
      if (children.length <= 8) return;
      const rows = [];
      for (let index = 8; index + 7 < children.length; index += 8) {{
        rows.push(children.slice(index, index + 8));
      }}
      rows.sort(compareRows);
      rows.forEach(row => row.forEach(element => grid.appendChild(element)));
    }});
  }};

  requestAnimationFrame(() => requestAnimationFrame(apply));
  setTimeout(apply, 130);
}})();
"""


def _install_planning_browser_helpers(self: ui_module.PlannerUI) -> None:
    ui.run_javascript(_SCROLL_SETUP_JS)
    ui.run_javascript(_resource_sort_script(self))


def _set_resource_sort(self: ui_module.PlannerUI, value: Any) -> None:
    self.planning_resource_sort = str(value or SORT_AVAIL_DESC)
    self.render_content.refresh()


def _render_planning(
    self: ui_module.PlannerUI,
    *,
    weekly_stats_provider: Any | None = None,
) -> None:
    sort_mode = str(getattr(self, "planning_resource_sort", SORT_AVAIL_DESC) or SORT_AVAIL_DESC)
    scoped_ui = ensure_scoped_ui(
        v17,
        scope_name="v17_planning",
        scoped_factories=("select",),
    )
    original_select = scoped_ui.base_factory("select")

    def select_proxy(options: Any, *args: Any, **kwargs: Any) -> Any:
        if kwargs.get("label") == "Classe":
            original_select(
                SORT_OPTIONS,
                label="Tri des ressources",
                value=sort_mode,
                on_change=lambda event: _set_resource_sort(self, event.value),
            ).classes("min-w-[240px]")
        return original_select(options, *args, **kwargs)

    with scoped_ui.override_factory("select", select_proxy):
        v17._render_planning(
            self,
            weekly_stats_provider=weekly_stats_provider,
        )

    ui.timer(0.08, lambda: _install_planning_browser_helpers(self), once=True)


def _new_resource_dialog(self: ui_module.PlannerUI) -> None:
    self.interaction_lock = True
    competencies = list(self.repo.competencies())

    with ui.dialog() as dialog, ui.card().classes("w-[680px] max-w-full"):
        ui.label("Nouvelle ressource").classes("text-xl font-bold")
        ui.label(
            "La ressource sera créée dans RessourcesMO. Elle devra ensuite recevoir un horaire standard dans Disponibilités avant de devenir planifiable."
        ).classes("text-sm muted")

        name = ui.input("Nom de la ressource").classes("w-full")
        resource_class = ui.select(
            v16.RESOURCE_CLASSES,
            label="Classe",
            clearable=True,
        ).classes("w-full")
        skills = ui.select(
            competencies,
            label="Compétences",
            multiple=True,
            with_input=True,
            clearable=True,
        ).classes("w-full")
        order = ui.number(
            "Ordre manuel (optionnel)",
            min=0,
            step=1,
        ).classes("w-full")
        note = ui.input("Note (optionnel)").classes("w-full")

        def save() -> None:
            resource_name = str(name.value or "").strip()
            if not resource_name:
                ui.notify("Le nom de la ressource est requis.", type="warning")
                return
            existing = {
                str(row.get("name") or "").strip().casefold()
                for row in self.repo.technicians()
                if str(row.get("name") or "").strip()
            }
            if resource_name.casefold() in existing:
                ui.notify("Une ressource avec ce nom existe déjà.", type="warning")
                return
            try:
                v16_refinements.update_resource_profile(
                    self.repo,
                    resource_name,
                    resource_class.value,
                    skills.value or [],
                    str(note.value or ""),
                    order.value,
                )
                dialog.close()
                self._after_write(
                    f"{resource_name} créée · ajoute maintenant son horaire standard dans Disponibilités"
                )
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        with ui.row().classes("w-full justify-end"):
            ui.button("Annuler", on_click=dialog.close).props("flat no-caps")
            ui.button("Créer", icon="person_add", on_click=save).props(
                "unelevated no-caps color=primary"
            )

    dialog.on("hide", lambda _: self._unlock())
    dialog.open()


def _manual_order_dialog(self: ui_module.PlannerUI) -> None:
    self.interaction_lock = True
    _ensure_manual_order_column(self.repo)
    profiles = v16_refinements.resource_profile_map(self.repo)
    technicians = sorted(
        self.repo.technicians(),
        key=lambda row: str(row.get("name") or "").casefold(),
    )

    with ui.dialog() as dialog, ui.card().classes("w-[720px] max-w-full"):
        ui.label("Ordre manuel des ressources").classes("text-xl font-bold")
        ui.label(
            "Utilise des nombres pour définir l'ordre dans chaque classe. Les valeurs peuvent être espacées (10, 20, 30...) afin de faciliter les insertions futures."
        ).classes("text-sm muted")

        controls: dict[str, Any] = {}
        for technician in technicians:
            name = str(technician.get("name") or "").strip()
            if not name:
                continue
            profile = profiles.get(name, {})
            with ui.row().classes("w-full items-center gap-3"):
                ui.label(name).classes("flex-1 font-medium")
                ui.label(str(profile.get("class") or v16.UNCLASSIFIED)).classes(
                    "w-[170px] text-xs muted"
                )
                controls[name] = ui.number(
                    "Ordre",
                    value=_order_number(profile.get("order")),
                    min=0,
                    step=1,
                ).classes("w-[130px]")

        def alpha_values() -> None:
            for index, name in enumerate(sorted(controls, key=str.casefold), start=1):
                controls[name].value = index * 10

        def save() -> None:
            try:
                current_profiles = v16_refinements.resource_profile_map(self.repo)
                for name, control in controls.items():
                    profile = current_profiles.get(name, {})
                    v16_refinements.update_resource_profile(
                        self.repo,
                        name,
                        None if profile.get("class") == v16.UNCLASSIFIED else profile.get("class"),
                        profile.get("competencies") or [],
                        str(profile.get("note") or ""),
                        control.value,
                    )
                dialog.close()
                self._after_write("Ordre manuel des ressources enregistré")
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        with ui.row().classes("w-full justify-between"):
            ui.button("Préremplir A → Z", icon="sort_by_alpha", on_click=alpha_values).props(
                "outline no-caps"
            )
            with ui.row().classes("gap-2"):
                ui.button("Annuler", on_click=dialog.close).props("flat no-caps")
                ui.button("Enregistrer", icon="save", on_click=save).props(
                    "unelevated no-caps color=primary"
                )

    dialog.on("hide", lambda _: self._unlock())
    dialog.open()


def _render_resources(self: ui_module.PlannerUI) -> None:
    with ui.row().classes("w-full justify-end gap-2"):
        ui.button(
            "Ordre manuel",
            icon="format_list_numbered",
            on_click=lambda: _manual_order_dialog(self),
        ).props("outline no-caps")
        ui.button(
            "Nouvelle ressource",
            icon="person_add",
            on_click=lambda: _new_resource_dialog(self),
        ).props("unelevated no-caps color=primary")
    v16_refinements._render_resources(self)


def install_v17_refinements() -> None:
    if getattr(ui_module.PlannerUI, "_v17_refinements_installed", False):
        return

    # Étend RessourcesMO avec un ordre manuel persistant. Le wrapper préserve
    # cette valeur lorsque l'ancien formulaire V1.6 ne la modifie pas.
    if RESOURCE_ORDER_FIELD not in v16_refinements.RESOURCE_PROFILE_HEADERS:
        v16_refinements.RESOURCE_PROFILE_HEADERS.append(RESOURCE_ORDER_FIELD)
    v16_refinements.update_resource_profile = _update_resource_profile_extended

    # Expose l'ordre dans le profil normalisé pour l'éditeur d'ordre manuel.
    original_profile_map = v16_refinements.resource_profile_map

    def resource_profile_map_with_order(repo: ExcelRepository) -> dict[str, dict[str, Any]]:
        result = original_profile_map(repo)
        raw = {
            str(row.get("Technicien") or "").strip(): row
            for row in v16_refinements._profile_records(repo)
        }
        for name, profile in result.items():
            profile["order"] = _order_number(raw.get(name, {}).get(RESOURCE_ORDER_FIELD))
        return result

    v16_refinements.resource_profile_map = resource_profile_map_with_order

    # RessourcesMO devient aussi une source de noms de ressources. Cela permet de
    # créer une ressource depuis l'application sans écrire dans le tableau historique
    # Configuration des listes. Elle reste non planifiable tant qu'aucun horaire
    # standard actif n'a été configuré dans Disponibilites.
    original_technicians = ExcelRepository.technicians

    def technicians_with_profiles(self: ExcelRepository) -> list[dict[str, Any]]:
        rows = list(original_technicians(self))
        known = {
            str(row.get("name") or "").strip().casefold()
            for row in rows
            if str(row.get("name") or "").strip()
        }
        try:
            profiles = v16_refinements._profile_records(self)
        except Exception:
            profiles = []
        for profile in profiles:
            name = str(profile.get("Technicien") or "").strip()
            if not name or name.casefold() in known:
                continue
            rows.append(
                {
                    "name": name,
                    "description": str(profile.get("Note") or ""),
                    "team": "",
                    "capacity": 0.0,
                }
            )
            known.add(name.casefold())
        return rows

    ExcelRepository.technicians = technicians_with_profiles

    previous_render_content = ui_module.PlannerUI._render_content

    def render_content(self: ui_module.PlannerUI) -> None:
        if self.current_page == "resources":
            _render_resources(self)
            return
        previous_render_content(self)

    ui_module.PlannerUI._render_content = render_content
    ui_module.PlannerUI.render_resources = _render_resources

    ui_module.PlannerUI.render_planning = _render_planning
    v13._render_operational_planning = _render_planning
    v15._render_operational_planning_v15 = _render_planning
    v15_refinements._render_planning = _render_planning
    v16._render_planning_v16 = _render_planning
    v16_refinements._render_planning = _render_planning

    ui_module.PlannerUI._v17_refinements_installed = True
