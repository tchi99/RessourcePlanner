from __future__ import annotations

import json
from datetime import date
from typing import Any

from nicegui import ui

from . import features
from . import ui as ui_module
from . import v13, v14_engine, v15, v15_engine, v15_refinements, v16, v16_refinements
from .bugfixes import schedulable_technicians
from .excel_repository import _date_from_any
from .operational_planning_cell_action import open_operational_planning_cell_shift
from .services import week_days


DROP_EVENT = "v17-planning-drop"


def _segment_by_id(repo: Any, segment_id: str) -> dict[str, Any] | None:
    return next(
        (
            row
            for row in v13.segment_records(repo, include_cancelled=False)
            if str(row.get("IDSegment") or "") == str(segment_id)
        ),
        None,
    )


def _actual_allocations(repo: Any) -> list[dict[str, Any]]:
    return [
        row
        for row in v15_engine.allocation_records(repo)
        if not v15_refinements.is_missing_allocation(row)
    ]


def _locked_hours(repo: Any, segment_id: str, *, exclude_allocation: str | None = None) -> float:
    total = 0.0
    for row in v15_engine.allocation_records(repo):
        if str(row.get("IDSegment") or "") != str(segment_id):
            continue
        if exclude_allocation and str(row.get("IDAllocation") or "") == str(exclude_allocation):
            continue
        if not v15_engine._truthy(row.get("Verrouillee")):
            continue
        if v15_refinements.is_missing_allocation(row):
            continue
        total += v13._number(row.get("Heures"))
    return round(total, 2)


def _validate_locked_total(
    repo: Any,
    segment_id: str,
    hours: Any,
    *,
    exclude_allocation: str | None = None,
) -> None:
    segment = _segment_by_id(repo, segment_id)
    if not segment:
        return
    planned = v13._number(segment.get("HeuresPrevues"))
    locked = _locked_hours(repo, segment_id, exclude_allocation=exclude_allocation)
    requested = v13._number(hours)
    if locked + requested > planned + 0.01:
        raise ValueError(
            f"Les quarts verrouillés dépasseraient les {planned:g} h prévues du segment "
            f"({locked:g} h déjà verrouillées + {requested:g} h)."
        )


def _make_draggable(element: Any, payload: str) -> Any:
    value = json.dumps(payload)
    element.props("draggable=true")
    element.classes("v17-draggable")
    element.on(
        "dragstart",
        js_handler=(
            "(event) => {"
            f"event.dataTransfer.setData('text/plain', {value});"
            "event.dataTransfer.effectAllowed = 'move';"
            "event.currentTarget.classList.add('v17-dragging');"
            "}"
        ),
    )
    element.on(
        "dragend",
        js_handler="(event) => event.currentTarget.classList.remove('v17-dragging')",
    )
    return element


def _make_drop_zone(element: Any, technician: str, day: date | None = None) -> Any:
    tech_json = json.dumps(technician)
    day_json = json.dumps(day.isoformat() if day else "")
    element.classes("v17-drop-zone")
    element.on(
        "dragover",
        js_handler=(
            "(event) => { event.preventDefault(); "
            "event.dataTransfer.dropEffect = 'move'; "
            "event.currentTarget.classList.add('v17-drop-hover'); }"
        ),
    )
    element.on(
        "dragleave",
        js_handler="(event) => event.currentTarget.classList.remove('v17-drop-hover')",
    )
    element.on(
        "drop",
        js_handler=(
            "(event) => { event.preventDefault(); "
            "event.currentTarget.classList.remove('v17-drop-hover'); "
            f"emitEvent('{DROP_EVENT}', {{"
            "payload: event.dataTransfer.getData('text/plain'), "
            f"technician: {tech_json}, date: {day_json}"
            "}); }"
        ),
    )
    return element


def _skill_message(repo: Any, technician: str, segment: dict[str, Any]) -> tuple[str, bool]:
    required = str(segment.get("CompetenceRequise") or "").strip()
    if not required:
        return "Aucune compétence requise spécifiée.", True
    profile_skills = v16_refinements.resource_competence_map(repo).get(technician, set())
    match = v16._normalized_text(required) in profile_skills
    if match:
        return f"Compétence {required} attribuée à {technician}.", True
    return f"Attention : {required} n'est pas attribuée à {technician}.", False


def _day_standard_load(repo: Any, technician: str, day: date) -> tuple[float, float, float]:
    capacity = v13._availability_hours(repo, technician, day)
    used = 0.0
    for row in _actual_allocations(repo):
        if str(row.get("Technicien") or "").strip() != technician:
            continue
        if _date_from_any(row.get("Date")) != day:
            continue
        if v15_engine._truthy(row.get("HorsHoraire")):
            continue
        used += v13._number(row.get("Heures"))
    return round(capacity, 2), round(used, 2), round(max(capacity - used, 0.0), 2)


def _eligible_segments_for_cell(repo: Any, technician: str, day: date) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for segment in v13.segment_records(repo, include_cancelled=False):
        if str(segment.get("Statut") or "") in {"Annulé", "Terminé"}:
            continue
        start, end = v13._segment_dates(segment)
        if not start or not end or not (start <= day <= end):
            continue
        current_tech = str(segment.get("Technicien") or "").strip()
        if current_tech and current_tech != technician:
            continue
        segment_id = str(segment.get("IDSegment") or "")
        lockable = v13._number(segment.get("HeuresPrevues")) - _locked_hours(repo, segment_id)
        if lockable <= 0.01:
            continue
        rows.append(segment)
    rows.sort(
        key=lambda row: (
            str(row.get("Priorite") or "Normale"),
            str(row.get("NumeroProjet") or ""),
            str(row.get("IDSegment") or ""),
        )
    )
    return rows


def _open_quick_allocation(self: ui_module.PlannerUI, technician: str, day: date) -> None:
    """Compatibility adapter until the V1.7 resource-row renderer is extracted."""
    open_operational_planning_cell_shift(self, technician, day)


def _move_allocation_same_resource(
    self: ui_module.PlannerUI,
    allocation: dict[str, Any],
    technician: str,
    target_day: date,
) -> None:
    segment = _segment_by_id(self.repo, str(allocation.get("IDSegment") or ""))
    if not segment:
        ui.notify("Segment parent introuvable.", type="negative")
        return
    start, end = v13._segment_dates(segment)
    if start and target_day < start or end and target_day > end:
        ui.notify(
            "La journée cible est hors de la fenêtre du segment. Modifie d'abord les dates du segment.",
            type="warning",
        )
        return

    capacity = v13._availability_hours(self.repo, technician, target_day)
    if capacity <= 0:
        _open_move_confirmation(self, allocation, technician, target_day)
        return

    try:
        v15_engine.update_manual_allocation(
            self.repo,
            str(allocation.get("IDAllocation") or ""),
            technician,
            target_day,
            allocation.get("Heures"),
            False,
            "Déplacé et verrouillé depuis le Planning opérationnel",
        )
        self._after_write(
            f"Quart déplacé au {target_day.strftime('%d/%m/%Y')} et verrouillé"
        )
    except Exception as exc:
        ui.notify(str(exc), type="negative")


def _open_move_confirmation(
    self: ui_module.PlannerUI,
    allocation: dict[str, Any],
    technician: str,
    target_day: date,
) -> None:
    self.interaction_lock = True
    state = features.availability_for_day(self.repo, technician, target_day)
    with ui.dialog() as dialog, ui.card().classes("w-[620px] max-w-full"):
        ui.label("Confirmer le déplacement hors horaire").classes("text-xl font-bold")
        ui.label(
            f"{technician} · {target_day.strftime('%d/%m/%Y')} · "
            f"{v13._number(allocation.get('Heures')):g} h"
        ).classes("font-semibold")
        ui.label(
            f"Disponibilité : {state.get('reason') or 'hors horaire standard'}."
        ).classes("text-sm text-orange-700")
        overtime = ui.checkbox("Confirmer comme quart hors horaire", value=True)

        def confirm() -> None:
            try:
                v15_engine.update_manual_allocation(
                    self.repo,
                    str(allocation.get("IDAllocation") or ""),
                    technician,
                    target_day,
                    allocation.get("Heures"),
                    bool(overtime.value),
                    "Déplacé manuellement depuis le Planning opérationnel",
                )
                dialog.close()
                self._after_write("Quart déplacé et verrouillé")
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        with ui.row().classes("w-full justify-end"):
            ui.button("Annuler", on_click=dialog.close).props("flat no-caps")
            ui.button("Confirmer", icon="check", on_click=confirm).props(
                "unelevated no-caps color=primary"
            )
    dialog.on("hide", lambda _: self._unlock())
    dialog.open()


def _split_allocation(
    self: ui_module.PlannerUI,
    allocation: dict[str, Any],
    target_technician: str,
    target_day: date,
    hors_horaire: bool,
) -> None:
    segment_id = str(allocation.get("IDSegment") or "")
    segment = _segment_by_id(self.repo, segment_id)
    if not segment:
        raise KeyError(f"Segment {segment_id} introuvable")
    amount = v13._number(allocation.get("Heures"))
    planned = v13._number(segment.get("HeuresPrevues"))
    if amount <= 0:
        raise ValueError("Le quart à fractionner ne contient aucune heure.")
    if amount >= planned - 0.01:
        v15_engine.update_manual_allocation(
            self.repo,
            str(allocation.get("IDAllocation") or ""),
            target_technician,
            target_day,
            amount,
            hors_horaire,
            "Segment réaffecté depuis le Planning opérationnel",
        )
        return

    if v15_engine._truthy(allocation.get("Verrouillee")):
        v15_engine.delete_manual_allocation(
            self.repo,
            str(allocation.get("IDAllocation") or ""),
        )

    v13.update_segment(
        self.repo,
        segment_id,
        {"HeuresPrevues": round(planned - amount, 2)},
    )
    new_id = v13.add_segment(
        self.repo,
        {
            "NoDemande": segment.get("NoDemande"),
            "NumeroProjet": segment.get("NumeroProjet"),
            "NomProjet": segment.get("NomProjet"),
            "Technicien": target_technician,
            "DateDebut": segment.get("DateDebut"),
            "DateFin": segment.get("DateFin"),
            "HeuresPrevues": amount,
            "Statut": "Planifié",
            "Description": (
                f"{segment.get('Description') or ''} — fractionné depuis {segment_id}"
            ).strip(" —"),
            "SourceEffortRow": segment.get("SourceEffortRow"),
            "CompetenceRequise": segment.get("CompetenceRequise"),
            "TypePlanification": segment.get("TypePlanification") or "Flexible",
            "Priorite": segment.get("Priorite") or "Normale",
            v15_refinements.SEGMENT_OVERTIME_FIELD: segment.get(
                v15_refinements.SEGMENT_OVERTIME_FIELD
            )
            or "Non",
        },
    )
    v15_engine.create_manual_allocation(
        self.repo,
        new_id,
        target_technician,
        target_day,
        amount,
        hors_horaire,
        f"Quart fractionné depuis {segment_id}",
    )


def _open_cross_resource_dialog(
    self: ui_module.PlannerUI,
    allocation: dict[str, Any],
    target_technician: str,
    target_day: date,
) -> None:
    segment = _segment_by_id(self.repo, str(allocation.get("IDSegment") or ""))
    if not segment:
        ui.notify("Segment parent introuvable.", type="negative")
        return
    start, end = v13._segment_dates(segment)
    if start and target_day < start or end and target_day > end:
        ui.notify(
            "La journée cible est hors de la fenêtre du segment. Modifie d'abord le segment.",
            type="warning",
        )
        return

    self.interaction_lock = True
    amount = v13._number(allocation.get("Heures"))
    planned = v13._number(segment.get("HeuresPrevues"))
    capacity = v13._availability_hours(self.repo, target_technician, target_day)
    skill_message, skill_match = _skill_message(self.repo, target_technician, segment)

    with ui.dialog() as dialog, ui.card().classes("w-[720px] max-w-full"):
        ui.label("Déplacer vers une autre ressource").classes("text-xl font-bold")
        ui.label(
            f"{segment.get('NumeroProjet') or '—'} · {amount:g} h → "
            f"{target_technician} · {target_day.strftime('%d/%m/%Y')}"
        ).classes("font-semibold")
        ui.label(skill_message).classes(
            "text-sm text-green-700" if skill_match else "text-sm text-amber-700"
        )
        ui.label(
            "Réaffecter le segment déplace aussi tout son reliquat automatique. "
            "Fractionner crée un nouveau segment uniquement pour les heures de ce quart."
        ).classes("text-sm muted")
        overtime = ui.checkbox(
            "Hors horaire standard",
            value=capacity <= 0,
        )

        def reassign() -> None:
            try:
                v15_engine.update_manual_allocation(
                    self.repo,
                    str(allocation.get("IDAllocation") or ""),
                    target_technician,
                    target_day,
                    amount,
                    bool(overtime.value),
                    "Segment réaffecté par glisser-déposer",
                )
                dialog.close()
                self._after_write(
                    f"Segment réaffecté à {target_technician}; quart verrouillé"
                )
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        def split() -> None:
            try:
                _split_allocation(
                    self,
                    allocation,
                    target_technician,
                    target_day,
                    bool(overtime.value),
                )
                dialog.close()
                self._after_write(
                    f"{amount:g} h fractionnées vers {target_technician}"
                )
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        with ui.row().classes("w-full justify-end"):
            ui.button("Annuler", on_click=dialog.close).props("flat no-caps")
            if planned > amount + 0.01:
                ui.button("Fractionner ce quart", icon="call_split", on_click=split).props(
                    "outline no-caps"
                )
            ui.button("Réaffecter le segment", icon="person_add", on_click=reassign).props(
                "unelevated no-caps color=primary"
            )

    dialog.on("hide", lambda _: self._unlock())
    dialog.open()


def _assign_backlog_segment(
    self: ui_module.PlannerUI,
    segment_id: str,
    technician: str,
    target_day: date | None,
) -> None:
    segment = _segment_by_id(self.repo, segment_id)
    if not segment:
        ui.notify(f"Segment {segment_id} introuvable.", type="negative")
        return
    if target_day:
        start, end = v13._segment_dates(segment)
        if start and target_day < start or end and target_day > end:
            ui.notify(
                "Le segment ne couvre pas cette journée. Dépose-le sur une ressource ou dans sa fenêtre de dates.",
                type="warning",
            )
            return
    try:
        v13.update_segment(
            self.repo,
            segment_id,
            {"Technicien": technician, "Statut": "Planifié"},
        )
        summary = v15_refinements.rebuild_allocations_refined(self.repo)
        message = f"{segment_id} assigné à {technician}"
        if summary.get("unallocated_hours", 0) > 0:
            message += f" · {summary['unallocated_hours']:g} h à confirmer hors horaire"
        self._after_write(message)
    except Exception as exc:
        ui.notify(str(exc), type="negative")


def _handle_drop(self: ui_module.PlannerUI, event: Any) -> None:
    args = getattr(event, "args", {}) or {}
    payload = str(args.get("payload") or "")
    technician = str(args.get("technician") or "").strip()
    target_day = _date_from_any(args.get("date"))
    if not payload or not technician:
        return

    if payload.startswith("segment:"):
        _assign_backlog_segment(self, payload.split(":", 1)[1], technician, target_day)
        return

    if not payload.startswith("allocation:"):
        return
    allocation_id = payload.split(":", 1)[1]
    allocation = v15_engine.allocation_by_id(self.repo, allocation_id)
    if not allocation or v15_refinements.is_missing_allocation(allocation):
        return

    source_technician = str(allocation.get("Technicien") or "").strip()
    if target_day is None:
        if source_technician == technician:
            return
        segment = _segment_by_id(self.repo, str(allocation.get("IDSegment") or ""))
        if segment:
            try:
                v13.update_segment(
                    self.repo,
                    str(segment.get("IDSegment") or ""),
                    {"Technicien": technician, "Statut": "Planifié"},
                )
                v15_refinements.rebuild_allocations_refined(self.repo)
                self._after_write(f"Segment réaffecté à {technician}")
            except Exception as exc:
                ui.notify(str(exc), type="negative")
        return

    if source_technician == technician:
        _move_allocation_same_resource(self, allocation, technician, target_day)
    else:
        _open_cross_resource_dialog(self, allocation, technician, target_day)


def _register_drop_handler(self: ui_module.PlannerUI) -> None:
    if getattr(self, "_v17_drop_handler_registered", False):
        return
    ui.on(DROP_EVENT, lambda event: _handle_drop(self, event))
    self._v17_drop_handler_registered = True


def _render_resource_row(
    self: ui_module.PlannerUI,
    tech: dict[str, Any],
    days: list[date],
    allocations: list[dict[str, Any]],
    segments: dict[str, dict[str, Any]],
    demands: dict[str, dict[str, Any]],
    pending: list[dict[str, Any]],
    week_stats: dict[str, dict[str, float]],
    project_filter: str,
    confirmation_filter: str,
) -> None:
    name = tech["name"]
    stats = week_stats.get(name, {})

    resource_cell = ui.column().classes("resource-cell p-3 justify-center gap-1")
    _make_drop_zone(resource_cell, name, None)
    with resource_cell:
        ui.label(name).classes("font-semibold")
        ui.label(
            f"{stats.get('prudent_free', 0):.1f} h libres / {stats.get('capacity', 0):.1f} h"
        ).classes("text-xs text-green-700")
        if stats.get("tentative", 0) > 0:
            ui.label(f"{stats['tentative']:.1f} h tentatives").classes(
                "text-[10px] text-amber-700"
            )
        ui.label("Déposer un travail ici pour l'assigner").classes("text-[9px] muted")

    for day in days:
        state = features.availability_for_day(self.repo, name, day)
        day_capacity = v13._availability_hours(self.repo, name, day)
        day_allocations = [
            row
            for row in allocations
            if str(row.get("Technicien") or "").strip() == name
            and row.get("Date") == day
            and (
                project_filter == v16.ALL_PROJECTS
                or v16._project_number_for_allocation(row) == project_filter
            )
        ]
        if confirmation_filter != v16.ALL_CONFIRMATIONS:
            day_allocations = [
                row
                for row in day_allocations
                if v15_refinements.demand_confirmation(
                    demands.get(str(row.get("NoDemande") or ""), {})
                )
                == confirmation_filter
            ]
        actual_allocations = [
            row
            for row in day_allocations
            if not v15_refinements.is_missing_allocation(row)
        ]
        pending_day = [
            row
            for row in pending
            if str(row.get("TechnicienPropose") or "").strip() == name
            and v15._pending_covers_day(row, day)
            and v13._availability_hours(self.repo, name, day) > 0
            and (
                project_filter == v16.ALL_PROJECTS
                or str(row.get("NumeroProjet") or "") == project_filter
            )
            and (
                confirmation_filter == v16.ALL_CONFIRMATIONS
                or v15_refinements.demand_confirmation(row) == confirmation_filter
            )
        ]
        planned = sum(v13._number(row.get("Heures")) for row in actual_allocations)
        standard_planned = sum(
            v13._number(row.get("Heures"))
            for row in actual_allocations
            if not v15_engine._truthy(row.get("HorsHoraire"))
        )
        overloaded = standard_planned > day_capacity + 0.01 and day_capacity >= 0
        free = max(day_capacity - standard_planned, 0.0)
        classes = "day-cell gap-1"
        if not state.get("available"):
            classes += " unavailable-cell"
        elif day.weekday() >= 5:
            classes += " weekend-cell"

        cell = ui.column().classes(classes)
        _make_drop_zone(cell, name, day)
        with cell:
            with ui.row().classes("w-full items-center justify-between gap-1"):
                with ui.column().classes("gap-0"):
                    if state.get("available") and state.get("hours"):
                        ui.label(state["hours"]).classes("text-[10px] availability-hours")
                    elif not state.get("available"):
                        ui.label(str(state.get("reason") or "Indisponible")).classes(
                            "text-[10px] unavailable-label"
                        )
                    if planned > 0 or day_capacity > 0:
                        css = (
                            "text-[10px] text-red-700 font-semibold"
                            if overloaded
                            else "text-[10px] muted"
                        )
                        ui.label(
                            f"{standard_planned:.1f}/{day_capacity:.1f} h · {free:.1f} h libres"
                        ).classes(css)
                ui.button(
                    icon="add",
                    on_click=lambda _, tech_name=name, target_day=day: _open_quick_allocation(
                        self, tech_name, target_day
                    ),
                ).props("flat dense round size=sm").tooltip("Planifier rapidement un quart")

            for allocation in day_allocations:
                segment = segments.get(str(allocation.get("IDSegment") or ""), {})
                demand = demands.get(str(allocation.get("NoDemande") or ""), {})
                style, label = v15_refinements._allocation_style(
                    allocation, demand, overloaded
                )
                card = ui.element("div").classes("shift-card").style(style)
                card.on(
                    "click",
                    lambda _, a=allocation: v15_refinements._open_allocation_dialog(
                        self, allocation=a
                    ),
                )
                if not v15_refinements.is_missing_allocation(allocation):
                    _make_draggable(
                        card,
                        f"allocation:{allocation.get('IDAllocation') or ''}",
                    )
                with card:
                    ui.label(
                        f"{allocation.get('NumeroProjet') or '—'} · {allocation.get('NomProjet') or ''}"
                    ).classes("text-xs font-semibold")
                    ui.label(
                        str(
                            segment.get("Description")
                            or allocation.get("IDSegment")
                            or "Allocation"
                        )
                    ).classes("text-xs")
                    suffix = (
                        " · 🔒"
                        if v15_engine._truthy(allocation.get("Verrouillee"))
                        else ""
                    )
                    if (
                        v15_refinements.demand_confirmation(demand) == "Tentative"
                        and "Tentative" not in label
                    ):
                        label = f"Tentative · {label}"
                    ui.label(
                        f"{v13._number(allocation.get('Heures')):.1f} h · {label}{suffix}"
                    ).classes("text-[11px] muted")

            for demand in pending_day:
                tentative = v15_refinements.demand_confirmation(demand) == "Tentative"
                style = (
                    "background:#fffbeb;border:2px dashed #d97706;opacity:.95;"
                    if tentative
                    else "background:#f3f4f6;border:2px dashed #9ca3af;opacity:.9;"
                )
                pending_card = ui.element("div").classes("shift-card").style(style)
                pending_card.on(
                    "click",
                    lambda _, d=demand: self.open_edit_request_dialog(d),
                )
                with pending_card:
                    ui.label(
                        f"{demand.get('NumeroProjet') or '—'} · {demand.get('NomProjet') or ''}"
                    ).classes("text-xs font-semibold")
                    ui.label(str(demand.get("Description") or "")).classes("text-xs")
                    ui.label(
                        f"{v15_refinements.demand_confirmation(demand)} · "
                        "en attente d'approbation · 0 h"
                    ).classes("text-[11px] text-gray-600")
                    ui.label("Cliquer pour ouvrir la demande").classes("text-[9px] muted")


def _render_planning(
    self: ui_module.PlannerUI,
    *,
    weekly_stats_provider: Any | None = None,
) -> None:
    _register_drop_handler(self)
    days = week_days(self.current_week)
    techs = schedulable_technicians(self.repo)
    class_map = v16.resource_class_map(self.repo)
    stats_provider = weekly_stats_provider or v16._weekly_resource_stats
    week_stats = stats_provider(self.repo, self.current_week)
    demands = v16._demand_lookup(self.repo)
    segments = {
        str(row.get("IDSegment") or ""): row
        for row in v13.segment_records(self.repo, include_cancelled=False)
    }
    allocations = [
        row
        for row in v15_engine.allocation_records(self.repo)
        if row.get("Date") and days[0] <= row["Date"] <= days[-1]
    ]
    unassigned = v15._unassigned_segments_for_week(self.repo, self.current_week)
    pending = v15._pending_demands_for_week(self.repo, self.current_week)

    class_filter = v16._filter_value(self, "planning_class_filter", v16.ALL_CLASSES)
    resource_filter = v16._filter_value(
        self, "planning_resource_filter", v16.ALL_RESOURCES
    )
    project_filter = v16._filter_value(
        self, "planning_project_filter", v16.ALL_PROJECTS
    )
    confirmation_filter = v16._filter_value(
        self, "planning_confirmation_filter", v16.ALL_CONFIRMATIONS
    )
    only_available = bool(v16._filter_value(self, "planning_only_available", False))

    project_values = sorted(
        {
            str(row.get("NumeroProjet") or "").strip()
            for row in [*allocations, *unassigned, *pending]
            if str(row.get("NumeroProjet") or "").strip()
        }
    )
    labels = v16_refinements._project_labels(self.repo)
    project_options = {v16.ALL_PROJECTS: v16.ALL_PROJECTS}
    for number in project_values:
        project_options[number] = labels.get(number, number)

    with ui.row().classes("w-full items-center"):
        with ui.column().classes("gap-0"):
            ui.label("Planning opérationnel").classes("text-2xl font-bold")
            ui.label(
                "Glisser un quart sur une autre journée pour le verrouiller; glisser sur une autre ressource permet de réaffecter ou fractionner."
            ).classes("muted")
        ui.space()
        ui.button(
            "Quart manuel",
            icon="add_task",
            on_click=lambda: v15_refinements._open_allocation_dialog(self),
        ).props("outline no-caps")
        ui.button(
            "Recalculer",
            icon="calculate",
            on_click=lambda: v15_refinements._recalculate(self),
        ).props("outline no-caps")
        ui.button(icon="chevron_left", on_click=self.previous_week).props("flat round")
        ui.button("Aujourd'hui", on_click=self.today_week).props("outline no-caps")
        ui.button(icon="chevron_right", on_click=self.next_week).props("flat round")
        ui.label(
            f"{days[0].strftime('%d %b')} – {days[-1].strftime('%d %b %Y')}"
        ).classes("font-semibold ml-2")

    with ui.card().classes("section-card w-full"):
        with ui.row().classes("w-full items-end gap-3"):
            ui.select(
                [v16.ALL_CLASSES, *v16.RESOURCE_CLASSES, v16.UNCLASSIFIED],
                label="Classe",
                value=class_filter,
                on_change=lambda event: v16._set_planning_filter(
                    self, "planning_class_filter", event.value
                ),
            ).classes("min-w-[190px]")
            ui.select(
                [v16.ALL_RESOURCES, *sorted(tech["name"] for tech in techs)],
                label="Ressource",
                value=resource_filter,
                with_input=True,
                on_change=lambda event: v16._set_planning_filter(
                    self, "planning_resource_filter", event.value
                ),
            ).classes("min-w-[210px]")
            ui.select(
                project_options,
                label="Projet",
                value=project_filter,
                with_input=True,
                on_change=lambda event: v16._set_planning_filter(
                    self, "planning_project_filter", event.value
                ),
            ).classes("min-w-[250px]")
            ui.select(
                [v16.ALL_CONFIRMATIONS, "Confirmée", "Tentative"],
                label="Confirmation",
                value=confirmation_filter,
                on_change=lambda event: v16._set_planning_filter(
                    self, "planning_confirmation_filter", event.value
                ),
            ).classes("min-w-[160px]")
            ui.checkbox(
                "Seulement avec capacité",
                value=only_available,
                on_change=lambda event: v16._set_planning_filter(
                    self, "planning_only_available", event.value
                ),
            )

    visible_unassigned = [
        segment
        for segment in unassigned
        if (
            project_filter == v16.ALL_PROJECTS
            or str(segment.get("NumeroProjet") or "") == project_filter
        )
        and (
            confirmation_filter == v16.ALL_CONFIRMATIONS
            or v15_refinements.demand_confirmation(
                demands.get(str(segment.get("NoDemande") or ""), {})
            )
            == confirmation_filter
        )
    ]
    if visible_unassigned:
        with ui.card().classes("section-card w-full"):
            ui.label(
                f"Travaux à planifier cette semaine ({len(visible_unassigned)})"
            ).classes("text-lg font-semibold")
            ui.label(
                "Tu peux utiliser Trouver une ressource ou glisser directement une carte sur le nom d'une ressource."
            ).classes("text-xs muted")
            with ui.row().classes("w-full gap-2 flex-wrap"):
                for segment in visible_unassigned[:20]:
                    competence = (
                        v14_engine.segment_competence(segment, demands)
                        or "Compétence non précisée"
                    )
                    required_class = v16._required_class(self.repo, segment)
                    card = ui.card().classes(
                        "p-3 min-w-[280px] max-w-[370px]"
                    )
                    _make_draggable(
                        card,
                        f"segment:{segment.get('IDSegment') or ''}",
                    )
                    with card:
                        ui.label(
                            f"{segment.get('NumeroProjet') or '—'} · {segment.get('NomProjet') or ''}"
                        ).classes("text-sm font-semibold")
                        ui.label(str(segment.get("Description") or "")).classes("text-xs")
                        ui.label(
                            f"{competence} · {required_class or 'Classe non déterminée'} · "
                            f"{v13._number(segment.get('HeuresPrevues')):g} h"
                        ).classes("text-xs text-orange-700")
                        with ui.row().classes("gap-1"):
                            ui.button(
                                "Trouver une ressource",
                                icon="recommend",
                                on_click=lambda _, s=segment: v16_refinements._open_recommendation_dialog(
                                    self, s
                                ),
                            ).props("unelevated dense no-caps color=primary")
                            ui.button(
                                "Segment",
                                icon="view_timeline",
                                on_click=lambda _, s=segment: v15_refinements._segment_dialog(
                                    self, segment=s
                                ),
                            ).props("flat dense no-caps")

    visible_pending = [
        demand
        for demand in pending
        if (
            project_filter == v16.ALL_PROJECTS
            or str(demand.get("NumeroProjet") or "") == project_filter
        )
        and (
            confirmation_filter == v16.ALL_CONFIRMATIONS
            or v15_refinements.demand_confirmation(demand) == confirmation_filter
        )
    ]
    if visible_pending:
        with ui.card().classes("section-card w-full"):
            ui.label(
                f"En attente d'approbation dans cette semaine ({len(visible_pending)})"
            ).classes("text-lg font-semibold")
            ui.label(
                "Ces besoins comptent 0 h de charge. Clique une carte pour ouvrir la demande."
            ).classes("text-xs muted")
            with ui.row().classes("w-full gap-2 flex-wrap"):
                for demand in visible_pending[:20]:
                    tentative = (
                        v15_refinements.demand_confirmation(demand) == "Tentative"
                    )
                    style = (
                        "background:#fffbeb;border:2px dashed #d97706;cursor:pointer;"
                        if tentative
                        else "background:#f9fafb;border:1px dashed #9ca3af;cursor:pointer;"
                    )
                    card = ui.card().classes(
                        "p-3 min-w-[250px] max-w-[340px]"
                    ).style(style)
                    card.on(
                        "click",
                        lambda _, d=demand: self.open_edit_request_dialog(d),
                    )
                    with card:
                        ui.label(
                            f"{demand.get('NumeroProjet') or '—'} · {demand.get('NomProjet') or ''}"
                        ).classes("text-sm font-semibold")
                        ui.label(
                            f"{v15_refinements.demand_confirmation(demand)} · "
                            f"{demand.get('CompetencesRequises') or 'Compétence non précisée'}"
                        ).classes("text-xs")
                        ui.label(
                            f"{self._date_text(demand.get('DateDebutSouhaitee'))} → "
                            f"{self._date_text(demand.get('DateFinSouhaitee'))}"
                        ).classes("text-xs muted")

    filtered_techs: list[dict[str, Any]] = []
    for tech in techs:
        name = tech["name"]
        group = class_map.get(name, v16.UNCLASSIFIED)
        if class_filter != v16.ALL_CLASSES and group != class_filter:
            continue
        if resource_filter != v16.ALL_RESOURCES and name != resource_filter:
            continue
        if only_available and week_stats.get(name, {}).get("prudent_free", 0) <= 0.01:
            continue
        filtered_techs.append(tech)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for tech in filtered_techs:
        group = class_map.get(tech["name"], v16.UNCLASSIFIED)
        grouped.setdefault(group, []).append(tech)
    for group in grouped:
        grouped[group].sort(
            key=lambda tech: (
                -week_stats.get(tech["name"], {}).get("prudent_free", 0.0),
                tech["name"],
            )
        )

    if not grouped:
        with ui.card().classes("section-card w-full"):
            ui.label("Aucune ressource ne correspond aux filtres.").classes("muted")
        return

    with ui.scroll_area().classes("w-full h-[calc(100vh-360px)]"):
        for group_name in sorted(grouped, key=v16._resource_group_order):
            group_techs = grouped[group_name]
            total_free = sum(
                week_stats.get(tech["name"], {}).get("prudent_free", 0.0)
                for tech in group_techs
            )
            total_capacity = sum(
                week_stats.get(tech["name"], {}).get("capacity", 0.0)
                for tech in group_techs
            )
            with ui.expansion(
                f"{group_name} · {len(group_techs)} ressource(s) · "
                f"{total_free:.1f} h libres / {total_capacity:.1f} h",
                icon="groups",
                value=True,
            ).classes("w-full"):
                with ui.grid(columns=8).classes("schedule-grid gap-0 w-full"):
                    with ui.column().classes("day-header p-3 justify-center"):
                        ui.label("Ressource").classes("font-semibold")
                    for day in days:
                        with ui.column().classes(
                            "day-header p-2 items-center justify-center"
                        ):
                            ui.label(day.strftime("%a").capitalize()).classes(
                                "text-xs uppercase muted"
                            )
                            ui.label(day.strftime("%d")).classes(
                                "text-xl font-semibold"
                            )
                    for tech in group_techs:
                        _render_resource_row(
                            self,
                            tech,
                            days,
                            allocations,
                            segments,
                            demands,
                            pending,
                            week_stats,
                            project_filter,
                            confirmation_filter,
                        )


def install_v17_features() -> None:
    if getattr(ui_module.PlannerUI, "_v17_features_installed", False):
        return

    original_create = v15_engine.create_manual_allocation
    original_update = v15_engine.update_manual_allocation

    def create_manual_allocation_guarded(
        repo: Any,
        segment_id: str,
        technician: str,
        day_value: Any,
        hours_value: Any,
        hors_horaire: bool = False,
        note: str = "",
    ) -> str:
        _validate_locked_total(repo, segment_id, hours_value)
        return original_create(
            repo,
            segment_id,
            technician,
            day_value,
            hours_value,
            hors_horaire,
            note,
        )

    def update_manual_allocation_guarded(
        repo: Any,
        identifier: str,
        technician: str,
        day_value: Any,
        hours_value: Any,
        hors_horaire: bool = False,
        note: str = "",
    ) -> None:
        allocation = v15_engine.allocation_by_id(repo, identifier)
        if allocation:
            _validate_locked_total(
                repo,
                str(allocation.get("IDSegment") or ""),
                hours_value,
                exclude_allocation=identifier,
            )
        original_update(
            repo,
            identifier,
            technician,
            day_value,
            hours_value,
            hors_horaire,
            note,
        )

    v15_engine.create_manual_allocation = create_manual_allocation_guarded
    v15_engine.update_manual_allocation = update_manual_allocation_guarded

    original_setup_style = ui_module.PlannerUI._setup_style

    def setup_style(self: ui_module.PlannerUI) -> None:
        original_setup_style(self)
        ui.add_head_html(
            """
            <style>
              .v17-draggable { cursor: grab; }
              .v17-dragging { opacity: .45; cursor: grabbing; }
              .v17-drop-zone { transition: outline .08s ease, background-color .08s ease; }
              .v17-drop-hover { outline: 2px dashed #2563eb !important; outline-offset: -3px; background:#eff6ff !important; }
            </style>
            """
        )

    ui_module.PlannerUI._setup_style = setup_style
    # Le renderer V1.7 reste disponible explicitement pour v17_refinements;
    # l'installer n'a plus à le propager dans les alias des couches précédentes.
    ui_module.PlannerUI._v17_features_installed = True
