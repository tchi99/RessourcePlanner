from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Mapping, Sequence

from .allocation_rules import fixed_segment_spread, flexible_segment_spread


CapacityKey = tuple[str, date]


@dataclass(frozen=True)
class SegmentInput:
    """Generic schedulable work segment independent from Excel and UI concepts."""

    segment_id: str
    resource_id: str
    start: date
    end: date
    hours: float
    plan_type: str = "Flexible"
    priority_rank: int = 2
    created_order: str = ""


@dataclass(frozen=True)
class LockedAllocationInput:
    segment_id: str
    resource_id: str
    day: date
    hours: float
    outside_schedule: bool = False


@dataclass(frozen=True)
class PlannedAllocation:
    segment_id: str
    resource_id: str
    day: date
    hours: float
    allocation_type: str
    locked: bool = False
    outside_schedule: bool = False


@dataclass(frozen=True)
class PlanResult:
    allocations: tuple[PlannedAllocation, ...]
    segment_count: int
    locked_allocation_count: int
    requested_hours: float
    allocated_hours: float
    unallocated_hours: float


def _segment_sort_key(segment: SegmentInput) -> tuple[object, ...]:
    return (
        segment.priority_rank,
        segment.start,
        segment.created_order,
        segment.segment_id,
    )


def _capacity_window(
    segment: SegmentInput,
    capacity_by_resource_day: Mapping[CapacityKey, float],
) -> list[tuple[date, float]]:
    if segment.end < segment.start:
        return []
    result: list[tuple[date, float]] = []
    cursor = segment.start
    while cursor <= segment.end:
        result.append(
            (
                cursor,
                max(float(capacity_by_resource_day.get((segment.resource_id, cursor), 0.0)), 0.0),
            )
        )
        cursor += timedelta(days=1)
    return result


def build_allocation_plan(
    segments: Sequence[SegmentInput],
    locked_allocations: Sequence[LockedAllocationInput],
    capacity_by_resource_day: Mapping[CapacityKey, float],
) -> PlanResult:
    """Build the V1.5 allocation policy without Excel, NiceGUI, or technician coupling.

    Callers are responsible for filtering inactive segments and resources before
    invoking this pure engine. The function keeps historical ordering semantics:
    locked/manual allocations first, then fixed segments, then flexible segments.
    Fixed work may overload standard capacity; flexible work never does.
    """
    active_segments = [segment for segment in segments if float(segment.hours) > 0]
    segment_map = {segment.segment_id: segment for segment in active_segments}

    preserved: list[PlannedAllocation] = []
    locked_by_segment: dict[str, float] = {}
    locked_used: dict[CapacityKey, float] = {}
    for allocation in locked_allocations:
        if allocation.segment_id not in segment_map or float(allocation.hours) <= 0:
            continue
        hours = float(allocation.hours)
        preserved.append(
            PlannedAllocation(
                segment_id=allocation.segment_id,
                resource_id=allocation.resource_id,
                day=allocation.day,
                hours=round(hours, 4),
                allocation_type="Locked",
                locked=True,
                outside_schedule=allocation.outside_schedule,
            )
        )
        locked_by_segment[allocation.segment_id] = (
            locked_by_segment.get(allocation.segment_id, 0.0) + hours
        )
        key = (allocation.resource_id, allocation.day)
        locked_used[key] = locked_used.get(key, 0.0) + hours

    fixed_segments = sorted(
        [segment for segment in active_segments if segment.plan_type == "Fixe"],
        key=_segment_sort_key,
    )
    flexible_segments = sorted(
        [segment for segment in active_segments if segment.plan_type != "Fixe"],
        key=_segment_sort_key,
    )

    fixed_used: dict[CapacityKey, float] = {}
    flexible_used: dict[CapacityKey, float] = {}
    allocations: list[PlannedAllocation] = list(preserved)

    for segment in fixed_segments:
        window = _capacity_window(segment, capacity_by_resource_day)
        locked_daily = {
            day: locked_used.get((segment.resource_id, day), 0.0)
            for day, _capacity in window
        }
        spread = fixed_segment_spread(
            segment.hours,
            window,
            locked_hours=locked_by_segment.get(segment.segment_id, 0.0),
            locked_by_day=locked_daily,
        )
        for day, hours in spread.items():
            key = (segment.resource_id, day)
            fixed_used[key] = fixed_used.get(key, 0.0) + hours
            allocations.append(
                PlannedAllocation(
                    segment_id=segment.segment_id,
                    resource_id=segment.resource_id,
                    day=day,
                    hours=round(hours, 4),
                    allocation_type="Fixe",
                )
            )

    for segment in flexible_segments:
        window = _capacity_window(segment, capacity_by_resource_day)
        locked_daily = {
            day: locked_used.get((segment.resource_id, day), 0.0)
            for day, _capacity in window
        }
        fixed_daily = {
            day: fixed_used.get((segment.resource_id, day), 0.0)
            for day, _capacity in window
        }
        flexible_daily = {
            day: flexible_used.get((segment.resource_id, day), 0.0)
            for day, _capacity in window
        }
        spread = flexible_segment_spread(
            segment.hours,
            window,
            locked_hours=locked_by_segment.get(segment.segment_id, 0.0),
            locked_by_day=locked_daily,
            fixed_by_day=fixed_daily,
            flexible_by_day=flexible_daily,
        )
        for day, hours in spread.items():
            key = (segment.resource_id, day)
            flexible_used[key] = flexible_used.get(key, 0.0) + hours
            allocations.append(
                PlannedAllocation(
                    segment_id=segment.segment_id,
                    resource_id=segment.resource_id,
                    day=day,
                    hours=round(hours, 4),
                    allocation_type="Flexible",
                )
            )

    allocations.sort(
        key=lambda item: (
            item.resource_id,
            item.day,
            0 if item.locked else 1,
            item.allocation_type,
            item.segment_id,
        )
    )
    requested = sum(float(segment.hours) for segment in active_segments)
    allocated = sum(float(item.hours) for item in allocations)
    return PlanResult(
        allocations=tuple(allocations),
        segment_count=len(active_segments),
        locked_allocation_count=len(preserved),
        requested_hours=round(requested, 4),
        allocated_hours=round(allocated, 4),
        unallocated_hours=round(max(requested - allocated, 0.0), 4),
    )
