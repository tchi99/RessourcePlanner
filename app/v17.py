from __future__ import annotations

from typing import Any

from nicegui import ui

from . import ui as ui_module
from . import v13, v15, v15_engine, v15_refinements, v16, v16_refinements
from .bugfixes import schedulable_technicians
from .operational_planning_cell_context_compat import operational_planning_cell_context
from .operational_planning_drop_handler import register_operational_planning_drop_handler
from .operational_planning_drop_handler_compat import (
    operational_planning_drop_handler_bindings,
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

    render_operational_planning_work_sections(
        self,
        unassigned,
        pending,
        demands,
        project_filter,
        confirmation_filter,
        bindings=work_sections_bindings,
    )

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
                        render_operational_planning_resource_row(
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
