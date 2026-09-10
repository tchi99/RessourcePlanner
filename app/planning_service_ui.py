from __future__ import annotations

from typing import Any

from nicegui import ui

from . import v15_refinements
from .application.runtime_services import planning_service
from . import ui as ui_module
from .ui_mutation_guard import MutationGate


RECALCULATE_REOPEN_SECONDS = 0.75


def _recalculate_gate(owner: ui_module.PlannerUI) -> MutationGate:
    gate = getattr(owner, "_planning_recalculate_gate", None)
    if not isinstance(gate, MutationGate):
        gate = MutationGate()
        owner._planning_recalculate_gate = gate
    return gate


def _recalculate_via_service(self: ui_module.PlannerUI) -> None:
    """UI adapter for the explicit planning application service.

    Presentation remains a NiceGUI concern; recalculation/orchestration crosses the
    application-service boundary. A completed gate remains closed briefly after a
    successful rebuild so queued double-click events are discarded, then reopens for a
    later deliberate recalculation.
    """
    gate = _recalculate_gate(self)
    actions = [getattr(self, "_planning_recalculate_action", None)]
    if not gate.begin(actions):
        return
    try:
        summary = planning_service(self.repo).rebuild()
        gate.succeed()
        ui.timer(
            RECALCULATE_REOPEN_SECONDS,
            lambda: gate.reset(actions),
            once=True,
        )
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
        gate.reset(actions)
        ui.notify(str(exc), type="negative")


def install_planning_service_ui() -> None:
    """Bind the historical Recalculer entry point to PlanningService.

    This is a transitional composition binding while the V1.x operational renderer
    still owns the button. It is installed once at composition time and keeps duplicate
    recalculation events out of the application service during the V1 cutover period.
    """
    if getattr(v15_refinements, "_planning_service_ui_installed", False):
        return

    v15_refinements._recalculate = _recalculate_via_service
    v15_refinements._planning_service_ui_installed = True
