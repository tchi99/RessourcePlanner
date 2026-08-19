from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Mapping, Sequence

from .allocation_rules import remaining_segment_hours, spread_hours


CapacityKey = tuple[str, date]
MISSING_ALLOCATION_TYPE = "Hors horaire requis"


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
    overtime_allowed: bool = False


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
    counts_as_allocated: bool = True


@dataclass(frozen=True)
class PlanResult:
    allocations: tuple[PlannedAllocation, ...]
    segment_count: int
    locked_allocation_count: int
    requested_hours: float
    allocated_hours: float
    unallocated_hours: float
    overtime_hours: float = 0.0
    missing_allocation_count: int = 0


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


def _outside_schedule_slots(
    segment: SegmentInput,
    hours: float,
    capacity_by_resource_day: Mapping[CapacityKey, float],
    eligible_by_resource_day: Mapping[CapacityKey, bool] | None,
    *,
    daily_limit: float,
) -> list[tuple[date, float]]:
    """Mirror the refined V1.5 fallback slots without embedding Excel concepts.

    Days with no standard capacity are preferred before standard-capacity days, then
    dates are ordered chronologically. The adapter can mark individual days as
    ineligible (for example vacation); when no eligibility map is supplied every day
    in the segment window is considered eligible.
    """
    if hours <= 0 or segment.end < segment.start:
        return []

    candidates: list[tuple[int, date]] = []
    cursor = segment.start
    while cursor <= segment.end:
        key = (segment.resource_id, cursor)
        eligible = (
            bool(eligible_by_resource_day.get(key, False))
            if eligible_by_resource_day is not None
            else True
        )
        if eligible:
            standard_capacity = max(float(capacity_by_resource_day.get(key, 0.0)), 0.0)
            priority = 0 if standard_capacity <= 0 else 1
            candidates.append((priority, cursor))
        cursor += timedelta(days=1)

    candidates.sort(key=lambda item: (item[0], item[1]))
    remaining = float(hours)
    result: list[tuple[date, float]] = []
    for _priority, day in candidates:
        if remaining <= 0.001:
            break
        amount = min(float(daily_limit), remaining)
        if amount > 0:
            result.append((day, round(amount, 4)))
            remaining -= amount
    return result


def build_allocation_plan(
    segments: Sequence[SegmentInput],
    locked_allocations: Sequence[LockedAllocationInput],
    capacity_by_resource_day: Mapping[CapacityKey, float],
    *,
    outside_schedule_eligible_by_resource_day: Mapping[CapacityKey, bool] | None = None,
    outside_schedule_daily_limit: float = 8.0,
    missing_allocation_type: str = MISSING_ALLOCATION_TYPE,
) -> PlanResult:
    """Build the current refined allocation policy without Excel or NiceGUI.

    Runtime semantics are intentionally reproduced here before replacing the legacy
    engine: locked/manual work first, then fixed segments, then flexible segments.
    Both fixed and flexible work first consume residual standard capacity. Any
    shortage is proposed in outside-schedule slots; it counts as real allocation only
    when that segment explicitly allows overtime. Otherwise a non-counting placeholder
    is retained so the shadow result can match what is persisted in AllocationsMO.
    """
    active_segments = [segment for segment in segments if float(segment.hours) > 0]
    segment_map = {segment.segment_id: segment for segment in active_segments}

    preserved: list[PlannedAllocation] = []
    locked_by_segment: dict[str, float] = {}
    normal_used: dict[CapacityKey, float] = {}
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
        normal_used[key] = normal_used.get(key, 0.0) + hours

    fixed_segments = sorted(
        [segment for segment in active_segments if segment.plan_type == "Fixe"],
        key=_segment_sort_key,
    )
    flexible_segments = sorted(
        [segment for segment in active_segments if segment.plan_type != "Fixe"],
        key=_segment_sort_key,
    )

    allocations: list[PlannedAllocation] = list(preserved)
    missing_total = 0.0
    overtime_total = sum(item.hours for item in preserved if item.outside_schedule)
    missing_count = 0

    def place_segment(segment: SegmentInput, allocation_type: str) -> None:
        nonlocal missing_total, overtime_total, missing_count
        remaining = remaining_segment_hours(
            segment.hours,
            locked_by_segment.get(segment.segment_id, 0.0),
        )
        if remaining <= 0 or segment.end < segment.start:
            return

        window = _capacity_window(segment, capacity_by_resource_day)
        residual: list[tuple[date, float]] = []
        for day, raw_capacity in window:
            room = max(
                raw_capacity - normal_used.get((segment.resource_id, day), 0.0),
                0.0,
            )
            if room > 0:
                residual.append((day, room))

        spread = spread_hours(remaining, residual)
        for day, hours in spread.items():
            key = (segment.resource_id, day)
            normal_used[key] = normal_used.get(key, 0.0) + hours
            allocations.append(
                PlannedAllocation(
                    segment_id=segment.segment_id,
                    resource_id=segment.resource_id,
                    day=day,
                    hours=round(hours, 4),
                    allocation_type=allocation_type,
                )
            )

        missing = max(remaining - sum(spread.values()), 0.0)
        if missing <= 0.001:
            return

        slots = _outside_schedule_slots(
            segment,
            missing,
            capacity_by_resource_day,
            outside_schedule_eligible_by_resource_day,
            daily_limit=outside_schedule_daily_limit,
        )
        placed_outside = 0.0
        for day, hours in slots:
            placed_outside += hours
            if segment.overtime_allowed:
                overtime_total += hours
                allocations.append(
                    PlannedAllocation(
                        segment_id=segment.segment_id,
                        resource_id=segment.resource_id,
                        day=day,
                        hours=round(hours, 4),
                        allocation_type=allocation_type,
                        outside_schedule=True,
                    )
                )
            else:
                missing_count += 1
                allocations.append(
                    PlannedAllocation(
                        segment_id=segment.segment_id,
                        resource_id=segment.resource_id,
                        day=day,
                        hours=round(hours, 4),
                        allocation_type=missing_allocation_type,
                        counts_as_allocated=False,
                    )
                )

        residual_missing = max(missing - placed_outside, 0.0)
        if segment.overtime_allowed:
            missing_total += residual_missing
        else:
            # The refined engine reports the complete shortage even when placeholder
            # rows successfully represent all suggested outside-schedule slots.
            missing_total += missing

    for segment in fixed_segments:
        place_segment(segment, "Fixe")
    for segment in flexible_segments:
        place_segment(segment, "Flexible")

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
    allocated = sum(float(item.hours) for item in allocations if item.counts_as_allocated)
    return PlanResult(
        allocations=tuple(allocations),
        segment_count=len(active_segments),
        locked_allocation_count=len(preserved),
        requested_hours=round(requested, 4),
        allocated_hours=round(allocated, 4),
        unallocated_hours=round(max(requested - allocated, missing_total), 4),
        overtime_hours=round(overtime_total, 4),
        missing_allocation_count=missing_count,
    )
