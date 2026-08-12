from __future__ import annotations

from typing import Any

from nicegui import ui

from . import ui as ui_module
from . import v13, v15, v15_refinements, v16, v16_refinements, v17
from .excel_repository import ExcelRepository


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


def _install_planning_browser_helpers() -> None:
    ui.run_javascript(_SCROLL_SETUP_JS)


def _render_planning(self: ui_module.PlannerUI) -> None:
    v17._render_planning(self)
    ui.timer(0.08, _install_planning_browser_helpers, once=True)


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


def _render_resources(self: ui_module.PlannerUI) -> None:
    with ui.row().classes("w-full justify-end"):
        ui.button(
            "Nouvelle ressource",
            icon="person_add",
            on_click=lambda: _new_resource_dialog(self),
        ).props("unelevated no-caps color=primary")
    v16_refinements._render_resources(self)


def install_v17_refinements() -> None:
    if getattr(ui_module.PlannerUI, "_v17_refinements_installed", False):
        return

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
