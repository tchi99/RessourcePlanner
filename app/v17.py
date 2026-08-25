from __future__ import annotations

from typing import Any

from nicegui import ui

from . import ui as ui_module
from . import v13, v15, v15_engine, v16
from .bugfixes import schedulable_technicians
from .operational_planning_cell_context_compat import operational_planning_cell_context
from .operational_planning_drop_handler import register_operational_planning_drop_handler
from .operational_planning_drop_handler_compat import (
    operational_planning_drop_handler_bindings,
)
from .operational_planning_header_filters import (
    render_operational_planning_header_filters,
    resolve_planning_filter_state,
)
from .operational_planning_header_filters_compat import (
    operational_planning_header_filter_bindings,
)
from .operational_planning_resource_groups import (
    group_operational_planning_resources,
    ordered_resource_group_names,
    resource_group_totals,
)
from .operational_planning_resource_groups_compat import (
    operational_planning_resource_group_bindings,
)
from .operational_planning_resource_row import render_operational_planning_resource_row
from .operational_planning_resource_row_compat import (
    operational_planning_resource_row_bindings,
)
from .operational_planning_work_sections import (
    render_operational_planning_work_sections,
)
from .operational_planning_work_sections_compat import (
    operational_planning_work_sections_bindings,
)
from .services import week_days


def _render_planning(
    self: ui_module.PlannerUI,
    *,
    weekly_stats_provider: Any | None = None,
) -> None:
    drop_bindings = operational_planning_drop_handler_bindings()
    register_operational_planning_drop_handler(self, bindings=drop_bindings)
    row_bindings = operational_planning_resource_row_bindings()
    work_sections_bindings = operational_planning_work_sections_bindings()
    header_filter_bindings = operational_planning_header_filter_bindings()
    resource_group_bindings = operational_planning_resource_group_bindings()

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

    filter_state = resolve_planning_filter_state(
        self,
        allocations,
        unassigned,
        pending,
        bindings=header_filter_bindings,
    )
    render_operational_planning_header_filters(
        self,
        days,
        techs,
        filter_state,
        bindings=header_filter_bindings,
    )

    render_operational_planning_work_sections(
        self,
        unassigned,
        pending,
        demands,
        filter_state.project_filter,
        filter_state.confirmation_filter,
        bindings=work_sections_bindings,
    )

    grouped = group_operational_planning_resources(
        techs,
        class_map,
        week_stats,
        filter_state.class_filter,
        filter_state.resource_filter,
        filter_state.only_available,
        bindings=resource_group_bindings,
    )

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
                            self,
                            tech,
                            days,
                            allocations,
                            segments,
                            demands,
                            pending,
                            week_stats,
                            filter_state.project_filter,
                            filter_state.confirmation_filter,
                            bindings=row_bindings,
                        )


def install_v17_features() -> None:
    if getattr(ui_module.PlannerUI, "_v17_features_installed", False):
        return

    cell_context = operational_planning_cell_context()
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
        cell_context.validate_locked_total(repo, segment_id, hours_value)
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
            cell_context.validate_locked_total(
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
