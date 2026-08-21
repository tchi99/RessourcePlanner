from __future__ import annotations

from datetime import datetime
from typing import Any


def _approve_demand_record_only(
    self: Any,
    number: str,
    comment: str = "",
) -> None:
    """Compatibility fallback for callers that still use ``repo.approve_demand``.

    Approval workflow orchestration now belongs to ``DemandService``. This method
    intentionally persists only the approval decision; it does not synchronize
    resource requirements and does not rebuild planning. Those operations are owned
    by the application service so they cannot be duplicated by historical wrappers.
    """
    self.update_demand(
        number,
        {
            "Statut": "En planification",
            "ApprouvePar": self.current_user,
            "DateApprobation": datetime.now(),
            "CommentaireApprobation": comment,
        },
        action="Approbation",
        comment=comment or "Demande approuvée",
    )


def install_demand_legacy_cleanup() -> None:
    """Neutralize stacked V1 approval wrappers after legacy composition.

    V1.5/V1.5 refinements historically wrapped ``ExcelRepository.approve_demand`` to
    synchronize segments and rebuild planning, while V1.8 added another batching
    wrapper. The primary UI no longer calls that method, but restoring one simple
    record-only compatibility method prevents a remaining caller from accidentally
    executing the old stacked workflow twice.

    The repository import is deliberately lazy so lightweight architecture/unit tests
    can import this module without xlwings.
    """
    from .excel_repository import ExcelRepository

    if getattr(ExcelRepository, "_demand_legacy_cleanup_installed", False):
        return

    ExcelRepository.approve_demand = _approve_demand_record_only
    ExcelRepository._demand_legacy_cleanup_installed = True
