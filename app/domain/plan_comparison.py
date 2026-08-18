from __future__ import annotations

from collections import defaultdict
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
