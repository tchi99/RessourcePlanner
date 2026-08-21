from __future__ import annotations

from contextlib import nullcontext
from collections.abc import Callable, Mapping
from typing import Any, ContextManager, Generic, TypeVar


RepositoryT = TypeVar("RepositoryT")


class DemandService(Generic[RepositoryT]):
    """Application service for demand approval/reapproval workflows.

    The service owns orchestration only. Storage mutation, synchronization of the
    approved operational requirements, planning rebuild and batching are injected
    by the composition layer so this module stays independent from NiceGUI, Excel,
    xlwings and versioned V1.x modules.
    """

    def __init__(
        self,
        repository: RepositoryT,
        *,
        approve_record: Callable[[RepositoryT, str, str], None],
        sync_approved_demand: Callable[[RepositoryT, str], None],
        rebuild_planning: Callable[[RepositoryT], Mapping[str, Any]],
        batch: Callable[[RepositoryT, str], ContextManager[Any]] | None = None,
    ) -> None:
        self._repository = repository
        self._approve_record = approve_record
        self._sync_approved_demand = sync_approved_demand
        self._rebuild_planning = rebuild_planning
        self._batch = batch

    def approve(self, number: str, comment: str = "") -> dict[str, Any]:
        """Approve or reapprove one demand and rebuild planning exactly once.

        The approved record is persisted first, then the operational requirements are
        synchronized to that approved version, then the selected planning engine is
        run once. A repository-specific batch context may collapse all physical saves
        into one write transaction.
        """
        context = (
            self._batch(self._repository, "approve demand")
            if self._batch is not None
            else nullcontext()
        )
        with context:
            self._approve_record(self._repository, number, comment)
            self._sync_approved_demand(self._repository, number)
            summary = self._rebuild_planning(self._repository)
        return dict(summary)
