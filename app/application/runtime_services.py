from __future__ import annotations

from contextlib import nullcontext
from typing import Any

from ..infrastructure.excel import ExcelDemandRepository, ExcelSegmentRepository
from ..infrastructure.excel.command_adapters import (
    ExcelApprovedDemandSyncAdapter,
    ExcelPlanningCommandAdapter,
)
from .demand_service import DemandService
from .planning_service import PlanningService
from .segment_service import SegmentService


def _runtime_batch(repository: Any, label: str):
    factory = getattr(repository, "batch_update", None)
    if callable(factory):
        return factory(label)
    return nullcontext()


def planning_service(repository: Any) -> PlanningService:
    """Build planning workflow through the storage-independent command port."""

    return PlanningService(ExcelPlanningCommandAdapter(repository))


def demand_service(repository: Any) -> DemandService:
    """Build demand workflows directly from portable ports/adapters."""

    demands = ExcelDemandRepository(repository)
    planning = ExcelPlanningCommandAdapter(repository)
    approved_sync = ExcelApprovedDemandSyncAdapter(repository, demands)
    return DemandService(
        demands,
        planning,
        approved_sync,
        current_user=str(getattr(repository, "current_user", "") or ""),
        batch=lambda label: _runtime_batch(repository, label),
    )


def segment_service(repository: Any) -> SegmentService:
    """Build segment workflows directly from portable ports/adapters."""

    return SegmentService(
        ExcelSegmentRepository(repository),
        ExcelPlanningCommandAdapter(repository),
    )
