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


def demand_service(repository: Any) -> DemandService[Any]:
    """Build demand workflows through portable repositories/command adapters."""

    demands = ExcelDemandRepository(repository)
    planning = ExcelPlanningCommandAdapter(repository)
    approved_sync = ExcelApprovedDemandSyncAdapter(repository, demands)
    return DemandService.from_repository_port(
        repository,
        demands,
        current_user=str(getattr(repository, "current_user", "") or ""),
        sync_approved_demand=lambda _repo, number: approved_sync.sync_approved(number),
        rebuild_planning=lambda _repo: planning.rebuild(),
        batch=_runtime_batch,
    )


def segment_service(repository: Any) -> SegmentService[Any]:
    """Build segment workflows through portable repository/command adapters."""

    segments = ExcelSegmentRepository(repository)
    planning = ExcelPlanningCommandAdapter(repository)
    return SegmentService.from_repository_port(
        repository,
        segments,
        rebuild_planning=lambda _repo: planning.rebuild(),
    )
