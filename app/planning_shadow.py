from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from . import v13, v14_engine, v15_engine
from .bugfixes import schedulable_technicians
from .domain.plan_comparison import (
    AllocationProjection,
    PlanComparison,
    compare_allocation_plans,
)
from .domain.planning_engine import (
    LockedAllocationInput,
    PlanResult,
    SegmentInput,
    build_allocation_plan,
)
from .excel_repository import ExcelRepository, _date_from_any


@dataclass(frozen=True)
class ShadowPlanReport:
    """Read-only comparison between persisted legacy allocations and the pure engine."""

    comparison: PlanComparison
    shadow_result: PlanResult
    unsupported_segment_ids: tuple[str, ...]


def _active_segment_rows(repo: ExcelRepository) -> list[dict[str, Any]]:
    schedulable = {row["name"] for row in schedulable_technicians(repo)}
    return [
        row
        for row in v13.segment_records(repo, include_cancelled=False)
        if str(row.get("Statut") or "") not in {"Annulé", "Terminé"}
        and str(row.get("Technicien") or "").strip() in schedulable
        and v13._number(row.get("HeuresPrevues")) > 0
    ]


def _segment_inputs(
    repo: ExcelRepository,
) -> tuple[list[SegmentInput], tuple[str, ...], dict[str, dict[str, Any]]]:
    demands = v14_engine.demand_lookup(repo)
    inputs: list[SegmentInput] = []
    unsupported: list[str] = []

    for row in _active_segment_rows(repo):
        segment_id = str(row.get("IDSegment") or "").strip()
        start, end = v13._segment_dates(row)
        if not segment_id or not start or not end:
            if segment_id:
                unsupported.append(segment_id)
            continue
        priority = v14_engine.segment_priority(row, demands)
        inputs.append(
            SegmentInput(
                segment_id=segment_id,
                resource_id=str(row.get("Technicien") or "").strip(),
                start=start,
                end=end,
                hours=v13._number(row.get("HeuresPrevues")),
                plan_type=v14_engine.segment_plan_type(row),
                priority_rank=v14_engine.PRIORITY_ORDER.get(priority, 2),
                created_order=str(row.get("DateCreation") or ""),
            )
        )

    return inputs, tuple(sorted(set(unsupported))), demands


def _locked_inputs(repo: ExcelRepository) -> list[LockedAllocationInput]:
    result: list[LockedAllocationInput] = []
    for row in v15_engine.allocation_records(repo):
        if not v15_engine._truthy(row.get("Verrouillee")):
            continue
        day = _date_from_any(row.get("Date"))
        resource_id = str(row.get("Technicien") or "").strip()
        segment_id = str(row.get("IDSegment") or "").strip()
        hours = v13._number(row.get("Heures"))
        if not day or not resource_id or not segment_id or hours <= 0:
            continue
        result.append(
            LockedAllocationInput(
                segment_id=segment_id,
                resource_id=resource_id,
                day=day,
                hours=hours,
                outside_schedule=v15_engine._truthy(row.get("HorsHoraire")),
            )
        )
    return result


def _capacity_snapshot(
    repo: ExcelRepository,
    segments: list[SegmentInput],
) -> dict[tuple[str, date], float]:
    """Read each resource/day capacity once for the shadow calculation."""
    result: dict[tuple[str, date], float] = {}
    for segment in segments:
        cursor = segment.start
        while cursor <= segment.end:
            key = (segment.resource_id, cursor)
            if key not in result:
                result[key] = v13._availability_hours(repo, segment.resource_id, cursor)
            cursor += timedelta(days=1)
    return result


def _legacy_projection(
    repo: ExcelRepository,
    included_segment_ids: set[str],
) -> list[AllocationProjection]:
    result: list[AllocationProjection] = []
    for row in v15_engine.allocation_records(repo):
        segment_id = str(row.get("IDSegment") or "").strip()
        if segment_id not in included_segment_ids:
            continue
        day = _date_from_any(row.get("Date"))
        resource_id = str(row.get("Technicien") or "").strip()
        hours = v13._number(row.get("Heures"))
        if not day or not resource_id or hours <= 0:
            continue
        locked = v15_engine._truthy(row.get("Verrouillee"))
        result.append(
            AllocationProjection(
                segment_id=segment_id,
                resource_id=resource_id,
                day=day,
                hours=hours,
                allocation_type="Locked" if locked else str(row.get("TypeAllocation") or ""),
                locked=locked,
                outside_schedule=v15_engine._truthy(row.get("HorsHoraire")),
            )
        )
    return result


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


def build_shadow_report(repo: ExcelRepository) -> ShadowPlanReport:
    """Compare the current persisted V1.5 plan to the pure engine without writing Excel.

    This deliberately does not call ``rebuild_allocations`` and never changes the
    workbook. It is intended as a migration diagnostic before the pure engine is
    allowed to replace the historical production calculation.
    """
    segments, unsupported, _demands = _segment_inputs(repo)
    locked = _locked_inputs(repo)
    capacities = _capacity_snapshot(repo, segments)
    shadow_result = build_allocation_plan(segments, locked, capacities)
    included_ids = {segment.segment_id for segment in segments}
    comparison = compare_allocation_plans(
        _legacy_projection(repo, included_ids),
        _shadow_projection(shadow_result),
    )
    return ShadowPlanReport(
        comparison=comparison,
        shadow_result=shadow_result,
        unsupported_segment_ids=unsupported,
    )
