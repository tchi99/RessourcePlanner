from __future__ import annotations

from datetime import date
from typing import Iterable


CapacityWindow = Iterable[tuple[date, float]]


def remaining_segment_hours(planned_hours: float, locked_hours: float = 0.0) -> float:
    """Return the automatic hours still to place after locked/manual allocations.

    Historical V1.5 behavior never lets locked hours create a negative remainder.
    """
    return max(float(planned_hours) - float(locked_hours), 0.0)


def residual_capacity(
    raw_capacity: float,
    *,
    locked_hours: float = 0.0,
    fixed_hours: float = 0.0,
    flexible_hours: float = 0.0,
) -> float:
    """Return standard capacity still available to automatic planning."""
    return max(
        float(raw_capacity)
        - float(locked_hours)
        - float(fixed_hours)
        - float(flexible_hours),
        0.0,
    )


def spread_hours(hours: float, capacities: CapacityWindow) -> dict[date, float]:
    """Spread hours proportionally without exceeding each day's capacity.

    This characterizes the allocation behavior used by the V1.4/V1.5 engines:
    the requested amount is capped by total supplied capacity, apportioned
    proportionally, rounded to four decimals, then any rounding remainder is
    filled into days that still have room.
    """
    normalized = [(day, max(float(capacity), 0.0)) for day, capacity in capacities]
    if hours <= 0 or not normalized:
        return {}

    total_capacity = sum(capacity for _, capacity in normalized)
    if total_capacity <= 0:
        return {}

    target = min(float(hours), total_capacity)
    result: dict[date, float] = {}
    remaining = target

    for index, (day, capacity) in enumerate(normalized):
        if index == len(normalized) - 1:
            amount = min(max(remaining, 0.0), capacity)
        else:
            amount = min(target * capacity / total_capacity, capacity)
        amount = round(max(amount, 0.0), 4)
        if amount > 0:
            result[day] = amount
            remaining -= amount

    if remaining > 0.001:
        for day, capacity in normalized:
            room = capacity - result.get(day, 0.0)
            if room <= 0:
                continue
            extra = min(room, remaining)
            result[day] = round(result.get(day, 0.0) + extra, 4)
            remaining -= extra
            if remaining <= 0.001:
                break

    return result


def total_allocated(spread: dict[date, float]) -> float:
    """Stable helper for allocation summaries and tests."""
    return round(sum(float(value) for value in spread.values()), 4)
