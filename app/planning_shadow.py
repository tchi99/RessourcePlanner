from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .application.repository_ports import PlanningReadRepositoryPort
from .domain.plan_comparison import AllocationProjection, PlanComparison, compare_allocation_plans
from .domain.plan_diagnostics import (
    SegmentAllocationBoundsSummary,
    summarize_segment_allocation_bounds,
)
from .domain.planning_engine import PlanResult, build_allocation_plan
from .domain.planning_projection import (
    PlanningCalculationSnapshot,
    project_planning_snapshot,
)
from .domain.planning_snapshot import PlanningSnapshot


@dataclass(frozen=True)
class ShadowPlanReport:
    """Comparison between persisted allocations and the pure engine."""

    comparison: PlanComparison
    shadow_result: PlanResult
    allocation_bounds: SegmentAllocationBoundsSummary
    unsupported_segment_ids: tuple[str, ...]


def build_planning_snapshot(reader: PlanningReadRepositoryPort) -> PlanningSnapshot:
    """Capture one immutable source snapshot through the persistence port."""

    return reader.capture()


def _shadow_projection(result: PlanResult) -> list[AllocationProjection]:
    return [
        AllocationProjection(
            segment_id=row.segment_id,
            resource_id=row.resource_id,
            day=row.day,
            hours=row.hours,
            allocation_type=row.allocation_type,
            locked=row.locked,
            outside_schedule=row.outside_schedule,
        )
        for row in result.allocations
    ]


def build_shadow_report_from_calculation(
    calculation: PlanningCalculationSnapshot,
) -> ShadowPlanReport:
    """Calculate the pure plan from fully typed, storage-neutral inputs."""

    shadow_result = build_allocation_plan(
        calculation.segments,
        calculation.locked_allocations,
        calculation.capacity_by_resource_day,
        preserve_locked_segment_ids=calculation.preserved_segment_ids,
        outside_schedule_eligible_by_resource_day=(
            calculation.outside_schedule_eligible_by_resource_day
        ),
    )
    comparison = compare_allocation_plans(
        calculation.persisted_allocations,
        _shadow_projection(shadow_result),
    )
    allocation_bounds = summarize_segment_allocation_bounds(
        calculation.segments,
        shadow_result.allocations,
    )
    return ShadowPlanReport(
        comparison=comparison,
        shadow_result=shadow_result,
        allocation_bounds=allocation_bounds,
        unsupported_segment_ids=calculation.unsupported_segment_ids,
    )


def build_shadow_report_from_snapshot(snapshot: PlanningSnapshot) -> ShadowPlanReport:
    """Project one source snapshot once, then calculate only from typed inputs."""

    return build_shadow_report_from_calculation(project_planning_snapshot(snapshot))


def build_shadow_report_from_repository(
    reader: PlanningReadRepositoryPort,
) -> ShadowPlanReport:
    """Capture once through the repository port, then calculate entirely in memory."""

    return build_shadow_report_from_snapshot(build_planning_snapshot(reader))


def build_shadow_report(repo: Any) -> ShadowPlanReport:
    """Backward-compatible Excel adapter for diagnostics/tools during V1 migration."""

    from .infrastructure.excel.planning_repository import ExcelPlanningReadRepository

    return build_shadow_report_from_repository(ExcelPlanningReadRepository(repo))
