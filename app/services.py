from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from .domain.calendar_rules import (
    business_days,
    effort_overlaps_day,
    week_days,
    week_start,
)
from .excel_repository import ExcelRepository


def weekly_load(
    repo: ExcelRepository, start: date
) -> list[dict[str, Any]]:
    end = start + timedelta(days=6)
    efforts = repo.efforts(include_closed=False)
    techs = {t["name"]: t for t in repo.technicians()}
    hours = defaultdict(float)

    for effort in efforts:
        tech = str(
            effort.get("Équipe/Technicien attitré") or ""
        ).strip()
        e_start = effort.get("Date de début")
        e_end = effort.get("Date de fin") or e_start
        total_hours = effort.get("Efforts Prévus") or 0.0

        if (
            not tech
            or not e_start
            or not e_end
            or e_end < start
            or e_start > end
        ):
            continue

        total_days = business_days(e_start, e_end)
        hours_per_day = (
            float(total_hours) / total_days
            if total_hours
            else 0.0
        )

        cursor = max(e_start, start)
        overlap_end = min(e_end, end)
        while cursor <= overlap_end:
            if cursor.weekday() < 5:
                hours[tech] += hours_per_day
            cursor += timedelta(days=1)

    result = []
    for name, info in techs.items():
        monthly_capacity = float(
            info.get("capacity") or 0.0
        )
        weekly_capacity = (
            monthly_capacity / 4.33
            if monthly_capacity
            else 0.0
        )
        planned = round(hours.get(name, 0.0), 1)
        pct = (
            round(planned / weekly_capacity * 100, 0)
            if weekly_capacity
            else None
        )
        result.append(
            {
                "name": name,
                "planned": planned,
                "weekly_capacity": round(
                    weekly_capacity, 1
                ),
                "pct": pct,
                "team": info.get("team") or "",
                "description": (
                    info.get("description") or ""
                ),
            }
        )

    result.sort(
        key=lambda r: (-(r["pct"] or -1), r["name"])
    )
    return result


def active_efforts_for_week(
    repo: ExcelRepository, start: date
) -> list[dict[str, Any]]:
    end = start + timedelta(days=6)
    return [
        e
        for e in repo.efforts(include_closed=False)
        if e.get("Date de début")
        and (
            e.get("Date de fin")
            or e.get("Date de début")
        )
        >= start
        and e.get("Date de début") <= end
    ]
