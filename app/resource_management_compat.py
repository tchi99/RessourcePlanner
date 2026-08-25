from __future__ import annotations

from typing import Any

from nicegui import ui

from . import ui as ui_module
from . import v16, v16_refinements
from .excel_repository import ExcelRepository


RESOURCE_ORDER_FIELD = "Ordre"


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
        order = ui.number("Ordre manuel (optionnel)", min=0, step=1).classes("w-full")
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


def install_resource_management_compat() -> None:
    if getattr(ui_module.PlannerUI, "_resource_management_installed", False):
        return

    if RESOURCE_ORDER_FIELD not in v16_refinements.RESOURCE_PROFILE_HEADERS:
        v16_refinements.RESOURCE_PROFILE_HEADERS.append(RESOURCE_ORDER_FIELD)
    v16_refinements.update_resource_profile = _update_resource_profile_extended

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
    ui_module.PlannerUI._resource_management_installed = True
