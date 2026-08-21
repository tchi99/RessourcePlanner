from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Generic, TypeVar


RepositoryT = TypeVar("RepositoryT")
RebuildPlanning = Callable[[RepositoryT], Mapping[str, Any]]


class PlanningService(Generic[RepositoryT]):
    """Application boundary for planning write workflows.

    The service deliberately knows nothing about NiceGUI, Excel, xlwings or the
    concrete planning engine. Those dependencies are supplied by the composition
    layer. This makes the same orchestration callable from the current desktop UI
    and, later, from FastAPI/Teams without moving business rules again.
    """

    def __init__(
        self,
        repository: RepositoryT,
        *,
        rebuild_planning: RebuildPlanning[RepositoryT],
    ) -> None:
        self._repository = repository
        self._rebuild_planning = rebuild_planning

    def rebuild(self) -> dict[str, Any]:
        """Recalculate and persist the authoritative operational plan.

        Exceptions are intentionally not translated here. The caller owns the
        presentation/transport policy (NiceGUI notification today, HTTP error later).
        """
        summary = self._rebuild_planning(self._repository)
        return dict(summary)
