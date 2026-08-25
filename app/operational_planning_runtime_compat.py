from __future__ import annotations

from . import ui as ui_module
from . import v15_engine
from .operational_planning_cell_context_compat import operational_planning_cell_context
from .operational_planning_runtime import install_operational_planning_runtime


def install_operational_planning_runtime_compat() -> None:
    """Compose operational-planning runtime seams from transitional V1.x adapters."""

    install_operational_planning_runtime(
        engine_module=v15_engine,
        planner_ui_cls=ui_module.PlannerUI,
        cell_context=operational_planning_cell_context(),
    )
