from __future__ import annotations

import hashlib
import json
from typing import Any

from nicegui import ui

from . import ui as ui_module
from . import v16, v16_refinements, v17_refinements, v17_sort_fix
from .bugfixes import schedulable_technicians
from .config import BASE_DIR
from .excel_repository import ExcelRepository


LOCAL_PREFERENCES_FILE = BASE_DIR / "user_preferences.json"
PREFERENCES_VERSION = 1


def _workbook_key(repo: ExcelRepository) -> str:
    """Return a non-reversible-ish key for per-workbook local preferences.

    The raw Windows/OneDrive path is deliberately not stored in the JSON file because
    it can contain a Windows username or organization name. The hash only separates
    preferences when the same installation is pointed at different workbooks.
    """
    raw = str(repo.path or "unconfigured").strip().casefold()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _load_preferences() -> dict[str, Any]:
    if not LOCAL_PREFERENCES_FILE.exists():
        return {"version": PREFERENCES_VERSION, "workbooks": {}}
    try:
        data = json.loads(LOCAL_PREFERENCES_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": PREFERENCES_VERSION, "workbooks": {}}
    if not isinstance(data, dict):
        return {"version": PREFERENCES_VERSION, "workbooks": {}}
    data.setdefault("version", PREFERENCES_VERSION)
    if not isinstance(data.get("workbooks"), dict):
        data["workbooks"] = {}
    return data


def _save_preferences(data: dict[str, Any]) -> None:
    data["version"] = PREFERENCES_VERSION
    data.setdefault("workbooks", {})
    temporary = LOCAL_PREFERENCES_FILE.with_suffix(".json.tmp")
    payload = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
    temporary.write_text(payload + "\n", encoding="utf-8")
    temporary.replace(LOCAL_PREFERENCES_FILE)


def _clean_order_map(raw: Any) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    result: dict[str, float] = {}
    for name, value in raw.items():
        technician = str(name or "").strip()
        if not technician:
            continue
        try:
            order = float(value)
        except (TypeError, ValueError):
            continue
        result[technician] = order
    return result


def _orders_section(repo: ExcelRepository, *, create: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    data = _load_preferences()
    workbooks = data.setdefault("workbooks", {})
    key = _workbook_key(repo)
    if create:
        section = workbooks.setdefault(key, {})
    else:
        section = workbooks.get(key, {})
        if not isinstance(section, dict):
            section = {}
    return data, section


def _write_local_orders(repo: ExcelRepository, updates: dict[str, Any]) -> bool:
    data, section = _orders_section(repo, create=True)
    current = _clean_order_map(section.get("resource_manual_order"))
    changed = False

    for name, value in updates.items():
        technician = str(name or "").strip()
        if not technician:
            continue
        if value in (None, ""):
            if technician in current:
                current.pop(technician, None)
                changed = True
            continue
        try:
            order = float(value)
        except (TypeError, ValueError):
            continue
        if current.get(technician) != order:
            current[technician] = order
            changed = True

    if not changed and "resource_manual_order" in section:
        return False

    section["resource_manual_order"] = current
    section["manual_order_storage"] = "local"
    _save_preferences(data)
    return True


def _local_order_map_factory(legacy_reader: Any):
    def local_order_map(repo: ExcelRepository) -> dict[str, float]:
        data, section = _orders_section(repo, create=False)
        if "resource_manual_order" in section:
            return _clean_order_map(section.get("resource_manual_order"))

        # One-time compatibility migration: if V1.7 already stored an order in
        # RessourcesMO, copy it to this user's local file and stop using Excel for it.
        # This avoids surprising the user by losing their current order after upgrade.
        try:
            legacy = _clean_order_map(legacy_reader(repo))
        except Exception:
            legacy = {}
        if legacy:
            workbooks = data.setdefault("workbooks", {})
            local_section = workbooks.setdefault(_workbook_key(repo), {})
            local_section["resource_manual_order"] = legacy
            local_section["manual_order_storage"] = "local"
            _save_preferences(data)
        return legacy

    return local_order_map


def _refresh_local_preference(self: ui_module.PlannerUI, message: str) -> None:
    # A local preference does not alter Excel, so do not trigger _after_write or an
    # Excel signature/save cycle. A UI refresh is sufficient.
    self.render_content.refresh()
    ui.notify(message, type="positive")


def _manual_order_dialog_local(self: ui_module.PlannerUI) -> None:
    self.interaction_lock = True
    profiles = v16_refinements.resource_profile_map(self.repo)
    manual = v17_refinements._resource_order_map(self.repo)
    technicians = sorted(
        self.repo.technicians(),
        key=lambda row: v17_sort_fix._alpha_key(str(row.get("name") or "")),
    )

    with ui.dialog() as dialog, ui.card().classes("w-[720px] max-w-full"):
        ui.label("Ordre manuel des ressources").classes("text-xl font-bold")
        ui.label(
            "Cet ordre est propre à ce poste/utilisateur et est enregistré dans "
            "user_preferences.json. Il ne modifie pas le classeur Excel partagé."
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
                    value=manual.get(name),
                    min=0,
                    step=1,
                ).classes("w-[130px]")

        def alpha_values() -> None:
            ordered_names = sorted(controls, key=v17_sort_fix._alpha_key)
            for index, name in enumerate(ordered_names, start=1):
                controls[name].value = index * 10

        def save() -> None:
            try:
                updates = {name: control.value for name, control in controls.items()}
                _write_local_orders(self.repo, updates)
                dialog.close()
                _refresh_local_preference(self, "Ordre manuel local enregistré")
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        with ui.row().classes("w-full justify-between"):
            ui.button(
                "Préremplir A → Z", icon="sort_by_alpha", on_click=alpha_values
            ).props("outline no-caps")
            with ui.row().classes("gap-2"):
                ui.button("Annuler", on_click=dialog.close).props("flat no-caps")
                ui.button("Enregistrer", icon="save", on_click=save).props(
                    "unelevated no-caps color=primary"
                )

    dialog.on("hide", lambda _: self._unlock())
    dialog.open()


def _move_manual_resource_local(
    self: ui_module.PlannerUI,
    technician: str,
    direction: int,
) -> None:
    if str(getattr(self, "planning_resource_sort", "")) != v17_refinements.SORT_MANUAL:
        return

    name = str(technician or "").strip()
    if not name or direction not in {-1, 1}:
        return

    class_map = v16.resource_class_map(self.repo)
    group = class_map.get(name, v16.UNCLASSIFIED)
    manual = v17_refinements._resource_order_map(self.repo)

    group_names = [
        str(row.get("name") or "").strip()
        for row in schedulable_technicians(self.repo)
        if class_map.get(str(row.get("name") or "").strip(), v16.UNCLASSIFIED) == group
    ]
    group_names.sort(
        key=lambda item: (
            0 if item in manual else 1,
            manual.get(item, 0.0),
            v17_sort_fix._alpha_key(item),
            item.casefold(),
        )
    )

    try:
        index = group_names.index(name)
    except ValueError:
        return
    target = index + direction
    if target < 0 or target >= len(group_names):
        ui.notify(
            "Cette ressource est déjà en première position."
            if direction < 0
            else "Cette ressource est déjà en dernière position.",
            type="info",
        )
        return

    neighbor = group_names[target]
    current_order = manual.get(name)
    neighbor_order = manual.get(neighbor)

    if (
        current_order is not None
        and neighbor_order is not None
        and float(current_order) != float(neighbor_order)
    ):
        updates = {name: neighbor_order, neighbor: current_order}
    else:
        group_names[index], group_names[target] = group_names[target], group_names[index]
        updates = {
            resource_name: position * 10
            for position, resource_name in enumerate(group_names, start=1)
        }

    try:
        _write_local_orders(self.repo, updates)
        _refresh_local_preference(self, f"{name} déplacé dans l'ordre manuel local")
    except Exception as exc:
        ui.notify(str(exc), type="negative")


def _new_resource_dialog_local(self: ui_module.PlannerUI) -> None:
    self.interaction_lock = True
    competencies = list(self.repo.competencies())

    with ui.dialog() as dialog, ui.card().classes("w-[680px] max-w-full"):
        ui.label("Nouvelle ressource").classes("text-xl font-bold")
        ui.label(
            "La ressource sera créée dans RessourcesMO. Son ordre manuel demeure une "
            "préférence locale et pourra ensuite être ajusté directement dans le planning."
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
                    None,
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


def install_v171_local_preferences() -> None:
    if getattr(ui_module.PlannerUI, "_v171_local_preferences_installed", False):
        return

    legacy_order_reader = v17_refinements._resource_order_map
    v17_refinements._resource_order_map = _local_order_map_factory(legacy_order_reader)

    # Both the numeric editor and the in-grid arrows are local-only from V1.7.1.
    v17_refinements._manual_order_dialog = _manual_order_dialog_local
    v17_refinements._new_resource_dialog = _new_resource_dialog_local
    v17_sort_fix._move_manual_resource = _move_manual_resource_local
    ui_module.PlannerUI.move_resource_manual = _move_manual_resource_local

    ui_module.PlannerUI._v171_local_preferences_installed = True
