from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Iterable


@dataclass(frozen=True)
class AllocationProjection:
    segment_id: str
    resource_id: str
    day: date
    hours: float
    allocation_type: str
    locked: bool = False
    outside_schedule: bool = False


@dataclass(frozen=True)
class AllocationDifference:
    segment_id: str
    resource_id: str
    day: date
    allocation_type: str
    locked: bool
    outside_schedule: bool
    legacy_hours: float
    shadow_hours: float


@dataclass(frozen=True)
class PlanComparison:
    matches: bool
    compared_keys: int
    differences: tuple[AllocationDifference, ...]


@dataclass(frozen=True)
class DifferenceSummary:
    """Aggregate mismatch diagnostics that intentionally omit business identifiers."""

    difference_count: int
    affected_segment_count: int
    legacy_only_key_count: int
    shadow_only_key_count: int
    changed_key_count: int
    redistributed_segment_count: int
    segment_total_delta_count: int
    legacy_difference_hours: float
    shadow_difference_hours: float
    net_shadow_minus_legacy_hours: float
    absolute_difference_hours: float
    difference_count_by_type: tuple[tuple[str, int], ...]
    net_hours_by_type: tuple[tuple[str, float], ...]


def _key(item: AllocationProjection) -> tuple[object, ...]:
    return (
        item.segment_id,
        item.resource_id,
        item.day,
        "Locked" if item.locked else item.allocation_type,
        bool(item.locked),
        bool(item.outside_schedule),
    )


def _aggregate(items: Iterable[AllocationProjection]) -> dict[tuple[object, ...], float]:
    result: dict[tuple[object, ...], float] = defaultdict(float)
    for item in items:
        result[_key(item)] += float(item.hours)
    return {key: round(value, 2) for key, value in result.items() if abs(value) > 0.004}


def compare_allocation_plans(
    legacy: Iterable[AllocationProjection],
    shadow: Iterable[AllocationProjection],
) -> PlanComparison:
    """Compare two allocation plans after normalizing to persisted Excel precision.

    The historical engine persists automatic allocations to two decimal places.
    Aggregating by semantic key also makes the comparison insensitive to generated
    allocation identifiers and row ordering.
    """
    legacy_map = _aggregate(legacy)
    shadow_map = _aggregate(shadow)
    keys = sorted(set(legacy_map) | set(shadow_map), key=str)
    differences: list[AllocationDifference] = []

    for key in keys:
        legacy_hours = legacy_map.get(key, 0.0)
        shadow_hours = shadow_map.get(key, 0.0)
        if abs(legacy_hours - shadow_hours) <= 0.01:
            continue
        segment_id, resource_id, day, allocation_type, locked, outside_schedule = key
        differences.append(
            AllocationDifference(
                segment_id=str(segment_id),
                resource_id=str(resource_id),
                day=day,  # type: ignore[arg-type]
                allocation_type=str(allocation_type),
                locked=bool(locked),
                outside_schedule=bool(outside_schedule),
                legacy_hours=legacy_hours,
                shadow_hours=shadow_hours,
            )
        )

    return PlanComparison(
        matches=not differences,
        compared_keys=len(keys),
        differences=tuple(differences),
    )


def summarize_differences(comparison: PlanComparison) -> DifferenceSummary:
    """Summarize mismatches without exposing resource, segment, project, or date values.

    A segment whose mismatch deltas sum to zero has the same total hours in both
    plans but a different distribution (for example, hours moved between days).
    This distinction is especially useful while validating a shadow planning engine.
    """
    differences = comparison.differences
    segment_net: dict[str, float] = defaultdict(float)
    count_by_type: Counter[str] = Counter()
    net_by_type: dict[str, float] = defaultdict(float)

    legacy_only = 0
    shadow_only = 0
    changed = 0
    legacy_difference_hours = 0.0
    shadow_difference_hours = 0.0
    absolute_difference_hours = 0.0

    for item in differences:
        legacy = float(item.legacy_hours)
        shadow = float(item.shadow_hours)
        delta = shadow - legacy
        segment_net[item.segment_id] += delta
        count_by_type[item.allocation_type] += 1
        net_by_type[item.allocation_type] += delta
        legacy_difference_hours += legacy
        shadow_difference_hours += shadow
        absolute_difference_hours += abs(delta)
        if legacy > 0 and shadow <= 0:
            legacy_only += 1
        elif shadow > 0 and legacy <= 0:
            shadow_only += 1
        else:
            changed += 1

    redistributed = sum(1 for delta in segment_net.values() if abs(delta) <= 0.01)
    total_delta_segments = sum(1 for delta in segment_net.values() if abs(delta) > 0.01)

    return DifferenceSummary(
        difference_count=len(differences),
        affected_segment_count=len(segment_net),
        legacy_only_key_count=legacy_only,
        shadow_only_key_count=shadow_only,
        changed_key_count=changed,
        redistributed_segment_count=redistributed,
        segment_total_delta_count=total_delta_segments,
        legacy_difference_hours=round(legacy_difference_hours, 2),
        shadow_difference_hours=round(shadow_difference_hours, 2),
        net_shadow_minus_legacy_hours=round(shadow_difference_hours - legacy_difference_hours, 2),
        absolute_difference_hours=round(absolute_difference_hours, 2),
        difference_count_by_type=tuple(sorted(count_by_type.items())),
        net_hours_by_type=tuple(
            sorted((name, round(value, 2)) for name, value in net_by_type.items())
        ),
    )
