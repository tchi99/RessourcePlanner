from __future__ import annotations

from datetime import date
from typing import Any

from nicegui import ui

from .operational_planning_resource_groups import (
    ResourceGroupingBindings,
    ordered_resource_group_names,
    resource_group_totals,
)
from .operational_planning_resource_row import (
    ResourceRowBindings,
    render_operational_planning_resource_row,
)


def render_operational_planning_grid(
    owner: Any,
    days: list[date],
    grouped: dict[str, list[dict[str, Any]]],
    allocations: list[dict[str, Any]],
    segments: dict[str, dict[str, Any]],
    demands: dict[str, dict[str, Any]],
    pending: list[dict[str, Any]],
    week_stats: dict[str, dict[str, Any]],
    project_filter: str,
    confirmation_filter: str,
    *,
    resource_group_bindings: ResourceGroupingBindings,
    row_bindings: ResourceRowBindings,
) -> None:
    """Render the grouped operational-planning grid from already prepared data."""

    if not grouped:
        with ui.card().classes("section-card w-full"):
            ui.label("Aucune ressource ne correspond aux filtres.").classes("muted")
        return

    with ui.scroll_area().classes("w-full h-[calc(100vh-360px)]"):
        for group_name in ordered_resource_group_names(
            grouped,
            bindings=resource_group_bindings,
        ):
            group_techs = grouped[group_name]
            total_free, total_capacity = resource_group_totals(
                group_techs,
                week_stats,
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
                        render_operational_planning_resource_row(
                            owner,
                            tech,
                            days,
                            allocations,
                            segments,
                            demands,
                            pending,
                            week_stats,
                            project_filter,
                            confirmation_filter,
                            bindings=row_bindings,
                        )
