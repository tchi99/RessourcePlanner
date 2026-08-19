from __future__ import annotations

from datetime import date, datetime, time as dt_time, timedelta
from typing import Any, Iterable


WEEKDAY_LABELS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]


def is_active(value: Any) -> bool:
    return str(value or "Oui").strip().lower() not in {"non", "no", "false", "0", "inactif"}


def _date_from_value(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        return (datetime(1899, 12, 30) + timedelta(days=float(value))).date()
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text[:19], fmt).date()
        except ValueError:
            continue
    return None


def _record_applies(record: dict[str, Any], day: date) -> bool:
    start = _date_from_value(record.get("DateDebut"))
    end = _date_from_value(record.get("DateFin"))
    return not ((start and day < start) or (end and day > end))


def _weekday_matches(record: dict[str, Any], day: date) -> bool:
    raw = str(record.get("JoursSemaine") or "").strip()
    if not raw:
        return True
    tokens = {part.strip().lower() for part in raw.replace(";", ",").split(",") if part.strip()}
    return WEEKDAY_LABELS[day.weekday()].lower() in tokens


def _fraction_to_hours(value: float) -> float:
    minutes = int(round((float(value) % 1.0) * 24 * 60)) % (24 * 60)
    return minutes / 60.0


def _time_hours(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.hour + value.minute / 60.0
    if isinstance(value, dt_time):
        return value.hour + value.minute / 60.0
    if isinstance(value, (int, float)):
        return _fraction_to_hours(float(value))
    text = str(value).strip()
    try:
        numeric = float(text.replace(",", "."))
    except ValueError:
        numeric = None
    if numeric is not None and 0 <= numeric < 1:
        return _fraction_to_hours(numeric)
    if ":" not in text:
        return None
    try:
        hour, minute = text.split(":", 1)
        return int(hour) + int(minute[:2]) / 60.0
    except (TypeError, ValueError):
        return None


def has_standard_schedule(records: Iterable[dict[str, Any]], resource_id: str) -> bool:
    resource_id = str(resource_id or "").strip()
    return any(
        str(row.get("Type") or "").strip() == "Horaire standard"
        and is_active(row.get("Actif"))
        and str(row.get("Technicien") or "").strip() == resource_id
        for row in records
    )


def availability_hours_for_day(
    records: Iterable[dict[str, Any]],
    resource_id: str,
    day: date,
) -> float:
    """Return historical schedulable hours using an in-memory availability snapshot."""
    rows = [row for row in records if is_active(row.get("Actif"))]
    resource_id = str(resource_id or "").strip()
    if not has_standard_schedule(rows, resource_id):
        return 0.0

    for row in rows:
        if str(row.get("Type") or "").strip() != "Jour férié":
            continue
        target = str(row.get("Technicien") or "").strip()
        if target and target != resource_id:
            continue
        if _record_applies(row, day):
            return 0.0

    for row in rows:
        if str(row.get("Type") or "").strip() != "Vacances":
            continue
        if str(row.get("Technicien") or "").strip() == resource_id and _record_applies(row, day):
            return 0.0

    standards = [
        row
        for row in rows
        if str(row.get("Type") or "").strip() == "Horaire standard"
        and str(row.get("Technicien") or "").strip() == resource_id
        and _record_applies(row, day)
        and _weekday_matches(row, day)
    ]
    if not standards:
        return 0.0

    start = _time_hours(standards[0].get("HeureDebut"))
    end = _time_hours(standards[0].get("HeureFin"))
    if start is None or end is None:
        return 0.0
    if end < start:
        end += 24.0
    return max(end - start, 0.0)


def outside_schedule_eligible_for_day(
    records: Iterable[dict[str, Any]],
    resource_id: str,
    day: date,
) -> bool:
    """Return whether refined V1.5 may suggest outside-schedule work that day.

    The production fallback excludes vacation, but allows weekends, holidays and
    evenings on normal workdays. Resources still require an explicit active standard
    schedule before they are schedulable at all.
    """
    rows = [row for row in records if is_active(row.get("Actif"))]
    resource_id = str(resource_id or "").strip()
    if not has_standard_schedule(rows, resource_id):
        return False
    for row in rows:
        if str(row.get("Type") or "").strip() != "Vacances":
            continue
        if str(row.get("Technicien") or "").strip() != resource_id:
            continue
        if _record_applies(row, day):
            return False
    return True
