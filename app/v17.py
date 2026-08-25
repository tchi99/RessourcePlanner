from __future__ import annotations

from typing import Any

from nicegui import ui

from . import ui as ui_module
from . import v15_engine
from .operational_planning_cell_context_compat import operational_planning_cell_context


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
    ui_module.PlannerUI._v17_features_installed = True
