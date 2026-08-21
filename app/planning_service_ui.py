from __future__ import annotations

from typing import Any

from nicegui import ui

from . import v15_refinements
from .application.runtime_services import planning_service
from . import ui as ui_module


def _recalculate_via_service(self: ui_module.PlannerUI) -> None:
    """UI adapter for the explicit planning application service.

    Presentation remains a NiceGUI concern; recalculation/orchestration crosses the
    application-service boundary. The runtime service resolves the engine selected by
    planning_cutover when the user clicks Recalculer.
    """
    try:
        summary = planning_service(self.repo).rebuild()
        self._after_write(
            f"Allocations recalculées : {summary['allocated_hours']:g} h allouées"
            + (
                f" · {summary['overtime_hours']:g} h hors horaire"
                if summary.get("overtime_hours")
                else ""
            )
            + (
                f" · {summary['unallocated_hours']:g} h à confirmer hors horaire"
                if summary.get("unallocated_hours", 0) > 0
                else ""
            )
        )
    except Exception as exc:
        ui.notify(str(exc), type="negative")


def install_planning_service_ui() -> None:
    """Bind the historical Recalculer entry point to PlanningService.

    This is a transitional composition binding while the V1.x operational renderer
    still lives in ``v15_refinements``/``v17``. It is installed once at composition
    time, never during a render. Tranche 4 can delete this binding when the planning
    page becomes an explicit UI module that calls PlanningService directly.
    """
    if getattr(v15_refinements, "_planning_service_ui_installed", False):
        return

    v15_refinements._recalculate = _recalculate_via_service
    v15_refinements._planning_service_ui_installed = True
