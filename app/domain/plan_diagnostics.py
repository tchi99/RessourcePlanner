from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Sequence

from .planning_engine import PlannedAllocation, SegmentInput


@dataclass(frozen=True)
class SegmentAllocationBoundsSummary:
    """Aggregate diagnostics for segment loads without exposing business identifiers."""

    overallocated_segment_count: int
    overallocated_hours: float
    locked_overallocated_segment_count: int
    locked_excess_hours: float
    max_segment_excess_hours: float


def summarize_segment_allocation_bounds(
    segments: Sequence[SegmentInput],
    allocations: Sequence[PlannedAllocation],
) -> SegmentAllocationBoundsSummary:
    requested_by_segment = {
        segment.segment_id: max(float(segment.hours), 0.0)
        for segment in segments
        if segment.segment_id and float(segment.hours) > 0
    }
    allocated_by_segment: dict[str, float] = defaultdict(float)
    locked_by_segment: dict[str, float] = defaultdict(float)

    for allocation in allocations:
        if allocation.segment_id not in requested_by_segment:
            continue
        if not allocation.counts_as_allocated or float(allocation.hours) <= 0:
            continue
        hours = float(allocation.hours)
        allocated_by_segment[allocation.segment_id] += hours
        if allocation.locked:
            locked_by_segment[allocation.segment_id] += hours

    overallocated_count = 0
    overallocated_hours = 0.0
    locked_overallocated_count = 0
    locked_excess_hours = 0.0
    max_segment_excess = 0.0

    for segment_id, requested in requested_by_segment.items():
        allocated = allocated_by_segment.get(segment_id, 0.0)
        excess = max(allocated - requested, 0.0)
        if excess > 0.01:
            overallocated_count += 1
            overallocated_hours += excess
            max_segment_excess = max(max_segment_excess, excess)

        locked = locked_by_segment.get(segment_id, 0.0)
        locked_excess = max(locked - requested, 0.0)
        if locked_excess > 0.01:
            locked_overallocated_count += 1
            locked_excess_hours += locked_excess

    return SegmentAllocationBoundsSummary(
        overallocated_segment_count=overallocated_count,
        overallocated_hours=round(overallocated_hours, 2),
        locked_overallocated_segment_count=locked_overallocated_count,
        locked_excess_hours=round(locked_excess_hours, 2),
        max_segment_excess_hours=round(max_segment_excess, 2),
    )
