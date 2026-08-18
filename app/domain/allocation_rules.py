from __future__ import annotations

from datetime import date
from typing import Iterable, Mapping


CapacityWindow = Iterable[tuple[date, float]]
HoursByDay = Mapping[date, float]


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


def fixed_segment_spread(
    planned_hours: float,
    capacities: CapacityWindow,
    *,
    locked_hours: float = 0.0,
    locked_by_day: HoursByDay | None = None,
) -> dict[date, float]:
    """Plan automatic hours for a historical V1.5 fixed segment.

    Locked/manual hours are subtracted from the segment total and consume standard
    capacity first. If the remaining standard capacity is insufficient, a fixed
    segment still places the missing hours across days that have a standard
    schedule. That overflow is intentional and is surfaced by the UI as overload.
    """
    remaining = remaining_segment_hours(planned_hours, locked_hours)
    if remaining <= 0:
        return {}

    locked_by_day = locked_by_day or {}
    raw_days = [
        (day, max(float(raw), 0.0))
        for day, raw in capacities
        if float(raw) > 0
    ]
    residual_days = [
        (
            day,
            residual_capacity(
                raw,
                locked_hours=float(locked_by_day.get(day, 0.0)),
            ),
        )
        for day, raw in raw_days
    ]
    residual_days = [(day, room) for day, room in residual_days if room > 0]

    result = spread_hours(remaining, residual_days)
    missing = max(remaining - sum(result.values()), 0.0)
    if missing > 0.001 and raw_days:
        overflow = spread_hours(missing, raw_days)
        for day, amount in overflow.items():
            result[day] = result.get(day, 0.0) + amount
    return result


def flexible_segment_spread(
    planned_hours: float,
    capacities: CapacityWindow,
    *,
    locked_hours: float = 0.0,
    locked_by_day: HoursByDay | None = None,
    fixed_by_day: HoursByDay | None = None,
    flexible_by_day: HoursByDay | None = None,
) -> dict[date, float]:
    """Plan automatic hours for a historical V1.5 flexible segment.

    Flexible work uses only residual standard capacity after locked/manual, fixed,
    and already placed flexible work. Unlike fixed work it never creates automatic
    overload; any shortage remains unallocated.
    """
    remaining = remaining_segment_hours(planned_hours, locked_hours)
    if remaining <= 0:
        return {}

    locked_by_day = locked_by_day or {}
    fixed_by_day = fixed_by_day or {}
    flexible_by_day = flexible_by_day or {}
    residual_days: list[tuple[date, float]] = []
    for day, raw in capacities:
        room = residual_capacity(
            raw,
            locked_hours=float(locked_by_day.get(day, 0.0)),
            fixed_hours=float(fixed_by_day.get(day, 0.0)),
            flexible_hours=float(flexible_by_day.get(day, 0.0)),
        )
        if room > 0:
            residual_days.append((day, room))

    return spread_hours(remaining, residual_days)


def total_allocated(spread: dict[date, float]) -> float:
    """Stable helper for allocation summaries and tests."""
    return round(sum(float(value) for value in spread.values()), 4)
