from __future__ import annotations

from datetime import date, timedelta
from typing import Any


def week_start(day: date | None = None) -> date:
    day = day or date.today()
    return day - timedelta(days=day.weekday())


def week_days(start: date) -> list[date]:
    return [start + timedelta(days=i) for i in range(7)]


def effort_overlaps_day(effort: dict[str, Any], day: date) -> bool:
    start = effort.get("Date de début")
    end = effort.get("Date de fin") or start
    return bool(start and end and start <= day <= end)


def business_days(start: date, end: date) -> int:
    if end < start:
        start, end = end, start
    count = 0
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            count += 1
        cursor += timedelta(days=1)
    return max(count, 1)
