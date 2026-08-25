from __future__ import annotations

from typing import Any

from nicegui import ui


DRAG_DROP_STYLE = """
<style>
  .v17-draggable { cursor: grab; }
  .v17-dragging { opacity: .45; cursor: grabbing; }
  .v17-drop-zone { transition: outline .08s ease, background-color .08s ease; }
  .v17-drop-hover { outline: 2px dashed #2563eb !important; outline-offset: -3px; background:#eff6ff !important; }
</style>
"""


def install_allocation_total_guard(engine_module: Any, cell_context: Any) -> None:
    """Guard manual allocation writes against the segment planned-hour total."""

    if getattr(engine_module, "_operational_planning_allocation_guard_installed", False):
        return

    original_create = engine_module.create_manual_allocation
    original_update = engine_module.update_manual_allocation

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
        allocation = engine_module.allocation_by_id(repo, identifier)
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

    engine_module.create_manual_allocation = create_manual_allocation_guarded
    engine_module.update_manual_allocation = update_manual_allocation_guarded
    engine_module._operational_planning_allocation_guard_installed = True


def install_operational_planning_style(planner_ui_cls: Any) -> None:
    """Install the planning drag/drop CSS without owning any planning renderer."""

    if getattr(planner_ui_cls, "_operational_planning_style_installed", False):
        return

    original_setup_style = planner_ui_cls._setup_style

    def setup_style(owner: Any) -> None:
        original_setup_style(owner)
        ui.add_head_html(DRAG_DROP_STYLE)

    planner_ui_cls._setup_style = setup_style
    planner_ui_cls._operational_planning_style_installed = True


def install_operational_planning_runtime(
    *,
    engine_module: Any,
    planner_ui_cls: Any,
    cell_context: Any,
) -> None:
    """Install the two remaining operational-planning runtime seams."""

    install_allocation_total_guard(engine_module, cell_context)
    install_operational_planning_style(planner_ui_cls)
