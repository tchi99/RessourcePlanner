from __future__ import annotations

from importlib import import_module
from typing import Any

from .planning_service import PlanningService


def _runtime_rebuild(repository: Any):
    """Resolve the currently installed compatibility alias only when executed."""
    v15_engine = import_module("app.v15_engine")
    return v15_engine.rebuild_allocations(repository)


def planning_service(repository: Any) -> PlanningService[Any]:
    """Build the runtime planning service against the currently selected engine.

    Engine import and lookup are deliberately lazy. Lightweight CI can import the
    application layer without NiceGUI, while the running application still resolves
    the authoritative ``v15_engine.rebuild_allocations`` alias after cutover has
    selected legacy/guarded/pure behavior.
    """
    return PlanningService(
        repository,
        rebuild_planning=_runtime_rebuild,
    )
