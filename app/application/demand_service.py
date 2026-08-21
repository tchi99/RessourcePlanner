from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import nullcontext
from typing import Any, ContextManager, Generic, TypeVar


RepositoryT = TypeVar("RepositoryT")


class DemandService(Generic[RepositoryT]):
    """Application service for workforce-demand lifecycle workflows.

    The service owns orchestration and workflow-level validation only. Storage
    mutation, synchronization of approved operational requirements, planning rebuild
    and batching are injected by the composition layer so this module stays
    independent from NiceGUI, Excel, xlwings and versioned V1.x modules.
    """

    def __init__(
        self,
        repository: RepositoryT,
        *,
        submit_record: Callable[[RepositoryT, str], None],
        approve_record: Callable[[RepositoryT, str, str], None],
        request_correction_record: Callable[[RepositoryT, str, str], None],
        cancel_record: Callable[[RepositoryT, str], None],
        sync_approved_demand: Callable[[RepositoryT, str], None],
        rebuild_planning: Callable[[RepositoryT], Mapping[str, Any]],
        batch: Callable[[RepositoryT, str], ContextManager[Any]] | None = None,
    ) -> None:
        self._repository = repository
        self._submit_record = submit_record
        self._approve_record = approve_record
        self._request_correction_record = request_correction_record
        self._cancel_record = cancel_record
        self._sync_approved_demand = sync_approved_demand
        self._rebuild_planning = rebuild_planning
        self._batch = batch

    def _context(self, label: str) -> ContextManager[Any]:
        return (
            self._batch(self._repository, label)
            if self._batch is not None
            else nullcontext()
        )

    def submit(self, number: str) -> None:
        """Submit a draft/corrected demand for approval."""
        with self._context("submit demand"):
            self._submit_record(self._repository, number)

    def approve(self, number: str, comment: str = "") -> dict[str, Any]:
        """Approve or reapprove one demand and rebuild planning exactly once.

        The approved record is persisted first, then the operational requirements are
        synchronized to that approved version, then the selected planning engine is
        run once. A repository-specific batch context may collapse all physical saves
        into one write transaction.
        """
        with self._context("approve demand"):
            self._approve_record(self._repository, number, comment)
            self._sync_approved_demand(self._repository, number)
            summary = self._rebuild_planning(self._repository)
        return dict(summary)

    def request_correction(self, number: str, comment: str) -> None:
        """Return a submitted demand for correction with a mandatory reason."""
        reason = str(comment or "").strip()
        if not reason:
            raise ValueError("Un commentaire de correction est requis.")
        with self._context("request demand correction"):
            self._request_correction_record(self._repository, number, reason)

    def cancel(self, number: str) -> None:
        """Cancel a demand using the current V1 lifecycle semantics.

        Cancellation intentionally does not add a planning rebuild here. This tranche
        preserves the existing V1 behavior; any future policy for cancelling already
        approved operational requirements must be decided explicitly rather than
        introduced as an architecture side effect.
        """
        with self._context("cancel demand"):
            self._cancel_record(self._repository, number)
