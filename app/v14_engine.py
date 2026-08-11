from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from . import v13
from .bugfixes import schedulable_technicians
from .excel_repository import ExcelRepository, MASTER_SHEETS, _date_from_any


ALLOCATION_SHEET = "AllocationsMO"
ALLOCATION_TABLE = "AllocationsMOTable"
ALLOCATION_HEADERS = [
    "IDAllocation",
    "IDSegment",
    "NoDemande",
    "NumeroProjet",
    "NomProjet",
    "Technicien",
    "Date",
    "Heures",
    "TypeAllocation",
    "CompetenceRequise",
    "Priorite",
    "DateGeneration",
]
SEGMENT_EXTRA_HEADERS = ["CompetenceRequise", "TypePlanification", "Priorite"]
PLAN_TYPES = ["Flexible", "Fixe"]
PRIORITIES = ["Urgent", "Élevée", "Normale", "Basse"]
PRIORITY_ORDER = {"Urgent": 0, "Élevée": 1, "Normale": 2, "Basse": 3}


def ensure_v14_sheets(repo: ExcelRepository) -> None:
    for header in SEGMENT_EXTRA_HEADERS:
        if header not in v13.SEGMENT_HEADERS:
            v13.SEGMENT_HEADERS.append(header)
    MASTER_SHEETS.add(v13.SEGMENT_SHEET)
    MASTER_SHEETS.add(ALLOCATION_SHEET)
    repo._ensure_sheet_table(v13.SEGMENT_SHEET, v13.SEGMENT_HEADERS, v13.SEGMENT_TABLE)
    repo._ensure_sheet_table(ALLOCATION_SHEET, ALLOCATION_HEADERS, ALLOCATION_TABLE)
    repo.save()


def demand_lookup(repo: ExcelRepository) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("NoDemande") or ""): row
        for row in repo.demands()
        if row.get("NoDemande")
    }


def segment_priority(segment: dict[str, Any], demands: dict[str, dict[str, Any]]) -> str:
    value = str(segment.get("Priorite") or "").strip()
    if value:
        return value
    demand = demands.get(str(segment.get("NoDemande") or ""), {})
    return str(demand.get("Priorite") or "Normale")


def segment_competence(segment: dict[str, Any], demands: dict[str, dict[str, Any]]) -> str:
    value = str(segment.get("CompetenceRequise") or "").strip()
    if value:
        return value
    demand = demands.get(str(segment.get("NoDemande") or ""), {})
    return str(demand.get("CompetencesRequises") or "").strip()


def segment_plan_type(segment: dict[str, Any]) -> str:
    value = str(segment.get("TypePlanification") or "Flexible").strip()
    return value if value in PLAN_TYPES else "Flexible"


def allocation_records(repo: ExcelRepository) -> list[dict[str, Any]]:
    with repo._lock:
        ensure_v14_sheets(repo)
        rows = repo._sheet_as_records(ALLOCATION_SHEET, "IDAllocation")
        result: list[dict[str, Any]] = []
        for row in rows:
            if not row.get("IDAllocation"):
                continue
            row["Date"] = _date_from_any(row.get("Date"))
            row["Heures"] = v13._number(row.get("Heures"))
            result.append(row)
        return result


def _segment_sort_key(
    segment: dict[str, Any], demands: dict[str, dict[str, Any]]
) -> tuple[Any, ...]:
    start, _ = v13._segment_dates(segment)
    return (
        PRIORITY_ORDER.get(segment_priority(segment, demands), 2),
        start or date.max,
        str(segment.get("DateCreation") or ""),
        str(segment.get("IDSegment") or ""),
    )


def _available_days(
    repo: ExcelRepository, technician: str, segment: dict[str, Any]
) -> list[tuple[date, float]]:
    start, end = v13._segment_dates(segment)
    if not start or not end:
        return []
    result: list[tuple[date, float]] = []
    cursor = start
    while cursor <= end:
        capacity = v13._availability_hours(repo, technician, cursor)
        if capacity > 0:
            result.append((cursor, capacity))
        cursor += timedelta(days=1)
    return result


def _spread_hours(hours: float, capacities: list[tuple[date, float]]) -> dict[date, float]:
    """Étale les heures proportionnellement sur toute la capacité disponible."""
    if hours <= 0 or not capacities:
        return {}
    total_capacity = sum(max(capacity, 0.0) for _, capacity in capacities)
    if total_capacity <= 0:
        return {}
    target = min(hours, total_capacity)
    result: dict[date, float] = {}
    remaining = target

    for index, (day, capacity) in enumerate(capacities):
        if index == len(capacities) - 1:
            amount = min(max(remaining, 0.0), capacity)
        else:
            amount = min(target * capacity / total_capacity, capacity)
        amount = round(max(amount, 0.0), 4)
        if amount > 0:
            result[day] = amount
            remaining -= amount

    # Corrige les écarts d'arrondi sans dépasser la capacité d'une journée.
    if remaining > 0.001:
        for day, capacity in capacities:
            room = capacity - result.get(day, 0.0)
            if room <= 0:
                continue
            extra = min(room, remaining)
            result[day] = round(result.get(day, 0.0) + extra, 4)
            remaining -= extra
            if remaining <= 0.001:
                break
    return result


def _payload(
    segment: dict[str, Any],
    day: date,
    hours: float,
    allocation_type: str,
    competence: str,
    priority: str,
    sequence: int,
    generation: datetime,
) -> dict[str, Any]:
    return {
        "IDAllocation": f"ALLOC-{generation.strftime('%Y%m%d%H%M%S')}-{sequence:05d}",
        "IDSegment": segment.get("IDSegment"),
        "NoDemande": segment.get("NoDemande"),
        "NumeroProjet": segment.get("NumeroProjet"),
        "NomProjet": segment.get("NomProjet"),
        "Technicien": segment.get("Technicien"),
        "Date": datetime.combine(day, datetime.min.time()),
        "Heures": round(hours, 2),
        "TypeAllocation": allocation_type,
        "CompetenceRequise": competence,
        "Priorite": priority,
        "DateGeneration": generation,
    }


def _write_allocations(repo: ExcelRepository, rows: list[dict[str, Any]]) -> None:
    with repo._lock:
        ensure_v14_sheets(repo)
        sheet = repo._book().sheets[ALLOCATION_SHEET]
        try:
            last_row = max(int(sheet.used_range.last_cell.row), 2)
        except Exception:
            last_row = 2
        sheet.range((2, 1), (last_row, len(ALLOCATION_HEADERS))).clear_contents()

        if rows:
            matrix = [[row.get(header) for header in ALLOCATION_HEADERS] for row in rows]
            sheet.range((2, 1), (1 + len(matrix), len(ALLOCATION_HEADERS))).value = matrix

        try:
            table = sheet.tables[ALLOCATION_TABLE]
            target_last = max(2, len(rows) + 1)
            table.resize(sheet.range((1, 1), (target_last, len(ALLOCATION_HEADERS))))
        except Exception:
            pass
        repo.save()


def rebuild_allocations(repo: ExcelRepository) -> dict[str, Any]:
    """Reconstruit les quarts journaliers depuis SegmentsMO.

    Les segments Fixe sont placés en premier. Ils peuvent créer une surcharge visible.
    Les segments Flexible utilisent ensuite uniquement la capacité résiduelle et sont
    étalés sur toute leur fenêtre de dates.
    """
    with repo._lock:
        ensure_v14_sheets(repo)
        demands = demand_lookup(repo)
        schedulable = {row["name"] for row in schedulable_technicians(repo)}
        segments = [
            row
            for row in v13.segment_records(repo, include_cancelled=False)
            if str(row.get("Statut") or "") != "Annulé"
            and str(row.get("Technicien") or "").strip() in schedulable
            and v13._number(row.get("HeuresPrevues")) > 0
        ]
        fixed = sorted(
            [row for row in segments if segment_plan_type(row) == "Fixe"],
            key=lambda row: _segment_sort_key(row, demands),
        )
        flexible = sorted(
            [row for row in segments if segment_plan_type(row) != "Fixe"],
            key=lambda row: _segment_sort_key(row, demands),
        )

        raw_capacity: dict[tuple[str, date], float] = {}
        fixed_used: dict[tuple[str, date], float] = {}
        flexible_used: dict[tuple[str, date], float] = {}
        rows: list[dict[str, Any]] = []
        generation = datetime.now()
        sequence = 0

        def capacity(technician: str, day: date) -> float:
            key = (technician, day)
            if key not in raw_capacity:
                raw_capacity[key] = v13._availability_hours(repo, technician, day)
            return raw_capacity[key]

        # Fixe = engagement déjà réservé. Chaque segment est étalé dans sa fenêtre
        # selon l'horaire brut, sans être effacé par un autre engagement fixe.
        for segment in fixed:
            tech = str(segment.get("Technicien") or "").strip()
            spread = _spread_hours(
                v13._number(segment.get("HeuresPrevues")),
                _available_days(repo, tech, segment),
            )
            competence = segment_competence(segment, demands)
            priority = segment_priority(segment, demands)
            for day, amount in spread.items():
                sequence += 1
                fixed_used[(tech, day)] = fixed_used.get((tech, day), 0.0) + amount
                rows.append(
                    _payload(
                        segment,
                        day,
                        amount,
                        "Fixe",
                        competence,
                        priority,
                        sequence,
                        generation,
                    )
                )

        # Flexible = utilise ce qui reste. Une journée déjà pleine reçoit 0 h et
        # n'affichera donc aucun shift pour ce segment.
        for segment in flexible:
            tech = str(segment.get("Technicien") or "").strip()
            start, end = v13._segment_dates(segment)
            if not start or not end:
                continue
            residual: list[tuple[date, float]] = []
            cursor = start
            while cursor <= end:
                available = max(
                    capacity(tech, cursor)
                    - fixed_used.get((tech, cursor), 0.0)
                    - flexible_used.get((tech, cursor), 0.0),
                    0.0,
                )
                if available > 0:
                    residual.append((cursor, available))
                cursor += timedelta(days=1)

            spread = _spread_hours(v13._number(segment.get("HeuresPrevues")), residual)
            competence = segment_competence(segment, demands)
            priority = segment_priority(segment, demands)
            for day, amount in spread.items():
                sequence += 1
                flexible_used[(tech, day)] = flexible_used.get((tech, day), 0.0) + amount
                rows.append(
                    _payload(
                        segment,
                        day,
                        amount,
                        "Flexible",
                        competence,
                        priority,
                        sequence,
                        generation,
                    )
                )

        rows.sort(
            key=lambda row: (
                str(row.get("Technicien") or ""),
                _date_from_any(row.get("Date")) or date.max,
                str(row.get("TypeAllocation") or ""),
                str(row.get("IDSegment") or ""),
            )
        )
        _write_allocations(repo, rows)

        requested = sum(v13._number(row.get("HeuresPrevues")) for row in segments)
        allocated = sum(v13._number(row.get("Heures")) for row in rows)
        return {
            "segments": len(segments),
            "allocations": len(rows),
            "requested_hours": round(requested, 2),
            "allocated_hours": round(allocated, 2),
            "unallocated_hours": round(max(requested - allocated, 0.0), 2),
        }


def allocated_by_segment(repo: ExcelRepository) -> dict[str, float]:
    result: dict[str, float] = {}
    for row in allocation_records(repo):
        ident = str(row.get("IDSegment") or "")
        result[ident] = result.get(ident, 0.0) + v13._number(row.get("Heures"))
    return result


def weekly_allocation_load(repo: ExcelRepository, start: date) -> list[dict[str, Any]]:
    techs = {row["name"]: row for row in schedulable_technicians(repo)}
    days = [start + timedelta(days=index) for index in range(7)]
    end = days[-1]
    allocations = [
        row
        for row in allocation_records(repo)
        if row.get("Date") and start <= row["Date"] <= end
    ]
    result: list[dict[str, Any]] = []
    for name, info in techs.items():
        capacity = sum(v13._availability_hours(repo, name, day) for day in days)
        planned = sum(
            v13._number(row.get("Heures"))
            for row in allocations
            if str(row.get("Technicien") or "").strip() == name
        )
        pct = round(planned / capacity * 100, 0) if capacity else None
        result.append(
            {
                "name": name,
                "planned": round(planned, 1),
                "weekly_capacity": round(capacity, 1),
                "pct": pct,
                "team": info.get("team") or "",
                "description": info.get("description") or "",
            }
        )
    result.sort(key=lambda row: (-(row["pct"] or -1), row["name"]))
    return result
