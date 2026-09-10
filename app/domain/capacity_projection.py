from __future__ import annotations

from datetime import date, timedelta


def _business_day_count(start: date, end: date) -> int:
    if end < start:
        return 0
    count = 0
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            count += 1
        cursor += timedelta(days=1)
    return count


def projected_hours_in_window(
    total_hours: float,
    range_start: date | None,
    range_end: date | None,
    window_start: date,
    window_end: date,
) -> float:
    """Spread a medium-term envelope over business days and clip it to a window.

    This is a forecast, not operational allocation. Weekends therefore do not absorb
    macro hours merely because they lie between the work-package dates.
    """

    hours = max(float(total_hours or 0.0), 0.0)
    if hours <= 0 or range_start is None:
        return 0.0
    range_end = range_end or range_start
    if range_end < range_start:
        range_start, range_end = range_end, range_start
    if window_end < window_start:
        window_start, window_end = window_end, window_start
    if range_end < window_start or range_start > window_end:
        return 0.0

    total_days = _business_day_count(range_start, range_end)
    if total_days <= 0:
        return 0.0
    overlap_start = max(range_start, window_start)
    overlap_end = min(range_end, window_end)
    overlap_days = _business_day_count(overlap_start, overlap_end)
    if overlap_days <= 0:
        return 0.0
    return round(hours * overlap_days / total_days, 2)
