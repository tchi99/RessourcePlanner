from __future__ import annotations

from contextlib import nullcontext
from importlib import import_module
from typing import Any

from ..infrastructure.excel import ExcelDemandRepository, ExcelSegmentRepository
from .demand_service import DemandService
from .planning_service import PlanningService
from .segment_service import SegmentService


def _runtime_rebuild(repository: Any):
    """Resolve the currently installed planning alias only when executed."""
    v15_engine = import_module("app.v15_engine")
    return v15_engine.rebuild_allocations(repository)


def _sync_approved_demand(
    repository: Any,
    demands: ExcelDemandRepository,
    number: str,
) -> None:
    """Bridge one approved demand to the remaining V1 synchronization helper.

    Raw Excel mappings are intentionally confined to this compatibility seam. The
    application service itself consumes ``DemandReadModel`` through the repository
    port and never receives the physical workbook row.
    """
    refinements = import_module("app.v15_refinements")
    demand = demands.raw_mapping(number)
    if demand is None:
        raise KeyError(f"Demande {number} introuvable après approbation")
    refinements._sync_segments_to_approved_demand(repository, demand)


def _runtime_batch(repository: Any, label: str):
    factory = getattr(repository, "batch_update", None)
    if callable(factory):
        return factory(label)
    return nullcontext()


def planning_service(repository: Any) -> PlanningService[Any]:
    """Build the runtime planning service against the authoritative engine alias."""
    return PlanningService(
        repository,
        rebuild_planning=_runtime_rebuild,
    )


def demand_service(repository: Any) -> DemandService[Any]:
    """Build demand workflows through the portable repository contract."""
    demands = ExcelDemandRepository(repository)
    return DemandService.from_repository_port(
        repository,
        demands,
        current_user=str(getattr(repository, "current_user", "") or ""),
        sync_approved_demand=lambda repo, number: _sync_approved_demand(
            repo,
            demands,
            number,
        ),
        rebuild_planning=_runtime_rebuild,
        batch=_runtime_batch,
    )


def segment_service(repository: Any) -> SegmentService[Any]:
    """Build segment workflows through the portable repository contract."""
    segments = ExcelSegmentRepository(repository)
    return SegmentService.from_repository_port(
        repository,
        segments,
        rebuild_planning=_runtime_rebuild,
    )
