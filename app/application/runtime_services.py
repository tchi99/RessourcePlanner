from __future__ import annotations

from typing import Any

from .planning_service import PlanningService
from .. import v15_engine


def planning_service(repository: Any) -> PlanningService[Any]:
    """Build the runtime planning service against the currently selected engine.

    The lambda intentionally resolves ``v15_engine.rebuild_allocations`` when the
    service executes, not when this factory runs. ``planning_cutover`` can therefore
    keep selecting legacy/guarded/pure through the existing compatibility alias while
    callers depend only on the application-service boundary.
    """
    return PlanningService(
        repository,
        rebuild_planning=lambda repo: v15_engine.rebuild_allocations(repo),
    )
