from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from nicegui import ui

from .operational_planning_cell_action import open_operational_planning_cell_shift


@dataclass(frozen=True)
class ResourceRowBindings:
    """Stable inputs required by the extracted operational-planning resource row.

    Historical V1.x helpers are supplied by the composition layer so this renderer
    remains physically independent from versioned modules while those helpers are
    progressively extracted as well.
    """

    make_drop_zone: Callable[[Any, str, date | None], Any]
    availability_for_day: Callable[[Any, str, date], dict[str, Any]]
    availability_hours: Callable[[Any, str, date], float]
    all_projects: str
    project_number_for_allocation: Callable[[dict[str, Any]], str]
    all_confirmations: str
    demand_confirmation: Callable[[dict[str, Any]], str]
    allocation_confirmation: Callable[[dict[str, Any], dict[str, Any]], str]
    is_missing_allocation: Callable[[dict[str, Any]], bool]
    pending_covers_day: Callable[[dict[str, Any], date], bool]
    number: Callable[[Any], float]
    truthy: Callable[[Any], bool]
    allocation_style: Callable[[dict[str, Any], dict[str, Any], bool], tuple[str, str]]
    open_allocation_dialog: Callable[..., None]
    make_draggable: Callable[[Any, str], Any]


def render_operational_planning_resource_row(
    owner: Any,
    tech: dict[str, Any],
    days: list[date],
    allocations: list[dict[str, Any]],
    segments: dict[str, dict[str, Any]],
    demands: dict[str, dict[str, Any]],
    pending: list[dict[str, Any]],
    week_stats: dict[str, dict[str, float]],
    project_filter: str,
    confirmation_filter: str,
    *,
    bindings: ResourceRowBindings,
) -> None:
    """Render one resource and its daily planning cells."""
    name = tech["name"]
    stats = week_stats.get(name, {})

    resource_cell = ui.column().classes("resource-cell p-3 justify-center gap-1")
    bindings.make_drop_zone(resource_cell, name, None)
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
        state = bindings.availability_for_day(owner.repo, name, day)
        day_capacity = bindings.availability_hours(owner.repo, name, day)
        day_allocations = [
            row
            for row in allocations
            if str(row.get("Technicien") or "").strip() == name
            and row.get("Date") == day
            and (
                project_filter == bindings.all_projects
                or bindings.project_number_for_allocation(row) == project_filter
            )
        ]
        if confirmation_filter != bindings.all_confirmations:
            day_allocations = [
                row
                for row in day_allocations
                if bindings.allocation_confirmation(
                    row,
                    demands.get(str(row.get("NoDemande") or ""), {}),
                )
                == confirmation_filter
            ]
        actual_allocations = [
            row for row in day_allocations if not bindings.is_missing_allocation(row)
        ]
        pending_day = [
            row
            for row in pending
            if str(row.get("TechnicienPropose") or "").strip() == name
            and bindings.pending_covers_day(row, day)
            and bindings.availability_hours(owner.repo, name, day) > 0
            and (
                project_filter == bindings.all_projects
                or str(row.get("NumeroProjet") or "") == project_filter
            )
            and (
                confirmation_filter == bindings.all_confirmations
                or bindings.demand_confirmation(row) == confirmation_filter
            )
        ]
        planned = sum(bindings.number(row.get("Heures")) for row in actual_allocations)
        standard_planned = sum(
            bindings.number(row.get("Heures"))
            for row in actual_allocations
            if not bindings.truthy(row.get("HorsHoraire"))
        )
        overloaded = standard_planned > day_capacity + 0.01 and day_capacity >= 0
        free = max(day_capacity - standard_planned, 0.0)
        classes = "day-cell gap-1"
        if not state.get("available"):
            classes += " unavailable-cell"
        elif day.weekday() >= 5:
            classes += " weekend-cell"

        cell = ui.column().classes(classes)
        bindings.make_drop_zone(cell, name, day)
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
                    on_click=lambda _, tech_name=name, target_day=day: open_operational_planning_cell_shift(
                        owner, tech_name, target_day
                    ),
                ).props("flat dense round size=sm").tooltip("Planifier rapidement un quart")

            for allocation in day_allocations:
                segment = segments.get(str(allocation.get("IDSegment") or ""), {})
                demand = demands.get(str(allocation.get("NoDemande") or ""), {})
                style, label = bindings.allocation_style(allocation, demand, overloaded)
                card = ui.element("div").classes("shift-card").style(style)
                card.on(
                    "click",
                    lambda _, a=allocation: bindings.open_allocation_dialog(
                        owner, allocation=a
                    ),
                )
                if not bindings.is_missing_allocation(allocation):
                    bindings.make_draggable(
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
                    suffix = " · 🔒" if bindings.truthy(allocation.get("Verrouillee")) else ""
                    effective_confirmation = bindings.allocation_confirmation(
                        allocation,
                        demand,
                    )
                    if effective_confirmation == "Tentative" and "Tentative" not in label:
                        label = f"Tentative · {label}"
                    ui.label(
                        f"{bindings.number(allocation.get('Heures')):.1f} h · {label}{suffix}"
                    ).classes("text-[11px] muted")

            for demand in pending_day:
                tentative = bindings.demand_confirmation(demand) == "Tentative"
                style = (
                    "background:#fffbeb;border:2px dashed #d97706;opacity:.95;"
                    if tentative
                    else "background:#f3f4f6;border:2px dashed #9ca3af;opacity:.9;"
                )
                pending_card = ui.element("div").classes("shift-card").style(style)
                pending_card.on(
                    "click",
                    lambda _, d=demand: owner.open_edit_request_dialog(d),
                )
                with pending_card:
                    ui.label(
                        f"{demand.get('NumeroProjet') or '—'} · {demand.get('NomProjet') or ''}"
                    ).classes("text-xs font-semibold")
                    ui.label(str(demand.get("Description") or "")).classes("text-xs")
                    ui.label(
                        f"{bindings.demand_confirmation(demand)} · "
                        "en attente d'approbation · 0 h"
                    ).classes("text-[11px] text-gray-600")
                    ui.label("Cliquer pour ouvrir la demande").classes("text-[9px] muted")
