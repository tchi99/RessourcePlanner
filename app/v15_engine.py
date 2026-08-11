from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from . import v13, v14_engine
from .bugfixes import schedulable_technicians
from .excel_repository import ExcelRepository, MASTER_SHEETS, _as_matrix, _date_from_any


ALLOCATION_EXTRA_HEADERS = ["Verrouillee", "HorsHoraire", "Note"]
TRUE_VALUES = {"oui", "yes", "true", "1", "x", "verrouille", "verrouillée"}


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in TRUE_VALUES


def ensure_v15_sheets(repo: ExcelRepository) -> None:
    """Étend AllocationsMO sans créer une nouvelle source de vérité.

    Les nouvelles colonnes servent à préserver les décisions manuelles lors d'un
    recalcul du moteur. Le marqueur par classeur évite de reformater Excel à chaque
    rafraîchissement de l'interface.
    """
    marker = str(repo.path or "")
    if getattr(repo, "_v15_ready_path", None) == marker:
        return

    for header in ALLOCATION_EXTRA_HEADERS:
        if header not in v14_engine.ALLOCATION_HEADERS:
            v14_engine.ALLOCATION_HEADERS.append(header)
    MASTER_SHEETS.add(v14_engine.ALLOCATION_SHEET)
    repo._ensure_sheet_table(
        v14_engine.ALLOCATION_SHEET,
        v14_engine.ALLOCATION_HEADERS,
        v14_engine.ALLOCATION_TABLE,
    )
    repo.save()
    repo._v15_ready_path = marker


def allocation_records(repo: ExcelRepository) -> list[dict[str, Any]]:
    ensure_v15_sheets(repo)
    rows = repo._sheet_as_records(v14_engine.ALLOCATION_SHEET, "IDAllocation")
    result: list[dict[str, Any]] = []
    for row in rows:
        if not row.get("IDAllocation"):
            continue
        row["Date"] = _date_from_any(row.get("Date"))
        row["Heures"] = v13._number(row.get("Heures"))
        result.append(row)
    return result


def allocation_by_id(repo: ExcelRepository, identifier: str) -> dict[str, Any] | None:
    return next(
        (
            row
            for row in allocation_records(repo)
            if str(row.get("IDAllocation") or "") == str(identifier)
        ),
        None,
    )


def _write_allocations(repo: ExcelRepository, rows: list[dict[str, Any]]) -> None:
    with repo._lock:
        ensure_v15_sheets(repo)
        headers = v14_engine.ALLOCATION_HEADERS
        sheet = repo._book().sheets[v14_engine.ALLOCATION_SHEET]
        try:
            last_row = max(int(sheet.used_range.last_cell.row), 2)
        except Exception:
            last_row = 2
        sheet.range((2, 1), (last_row, len(headers))).clear_contents()

        if rows:
            matrix: list[list[Any]] = []
            for row in rows:
                line = []
                for header in headers:
                    value = row.get(header)
                    if header == "Date":
                        parsed = _date_from_any(value)
                        value = datetime.combine(parsed, datetime.min.time()) if parsed else None
                    line.append(value)
                matrix.append(line)
            sheet.range((2, 1), (1 + len(matrix), len(headers))).value = matrix

        try:
            table = sheet.tables[v14_engine.ALLOCATION_TABLE]
            target_last = max(2, len(rows) + 1)
            table.resize(sheet.range((1, 1), (target_last, len(headers))))
        except Exception:
            pass
        repo.save()


def _auto_payload(
    segment: dict[str, Any],
    day: date,
    hours: float,
    allocation_type: str,
    competence: str,
    priority: str,
    sequence: int,
    generation: datetime,
) -> dict[str, Any]:
    row = v14_engine._payload(
        segment,
        day,
        hours,
        allocation_type,
        competence,
        priority,
        sequence,
        generation,
    )
    row["Verrouillee"] = "Non"
    row["HorsHoraire"] = "Non"
    row["Note"] = ""
    return row


def rebuild_allocations(repo: ExcelRepository) -> dict[str, Any]:
    """Reconstruit uniquement les allocations automatiques.

    Les lignes marquées Verrouillee=Oui sont conservées. Elles consomment la
    capacité avant les segments fixes et flexibles. Les heures verrouillées d'un
    segment sont également soustraites de ses heures à répartir afin qu'un quart
    déplacé manuellement ne soit pas recréé ailleurs en double.
    """
    with repo._lock:
        ensure_v15_sheets(repo)
        demands = v14_engine.demand_lookup(repo)
        schedulable = {row["name"] for row in schedulable_technicians(repo)}
        active_segments = [
            row
            for row in v13.segment_records(repo, include_cancelled=False)
            if str(row.get("Statut") or "") not in {"Annulé", "Terminé"}
        ]
        segment_map = {
            str(row.get("IDSegment") or ""): row
            for row in active_segments
            if row.get("IDSegment")
        }

        preserved: list[dict[str, Any]] = []
        locked_by_segment: dict[str, float] = {}
        locked_used: dict[tuple[str, date], float] = {}
        for row in allocation_records(repo):
            if not _truthy(row.get("Verrouillee")):
                continue
            segment_id = str(row.get("IDSegment") or "")
            if segment_id not in segment_map:
                continue
            day = _date_from_any(row.get("Date"))
            tech = str(row.get("Technicien") or "").strip()
            hours = v13._number(row.get("Heures"))
            if not day or not tech or hours <= 0:
                continue
            clean = dict(row)
            clean["Date"] = day
            clean["Heures"] = round(hours, 2)
            clean["Verrouillee"] = "Oui"
            clean["HorsHoraire"] = "Oui" if _truthy(row.get("HorsHoraire")) else "Non"
            preserved.append(clean)
            locked_by_segment[segment_id] = locked_by_segment.get(segment_id, 0.0) + hours
            locked_used[(tech, day)] = locked_used.get((tech, day), 0.0) + hours

        segments = [
            row
            for row in active_segments
            if str(row.get("Technicien") or "").strip() in schedulable
            and v13._number(row.get("HeuresPrevues")) > 0
        ]
        fixed = sorted(
            [row for row in segments if v14_engine.segment_plan_type(row) == "Fixe"],
            key=lambda row: v14_engine._segment_sort_key(row, demands),
        )
        flexible = sorted(
            [row for row in segments if v14_engine.segment_plan_type(row) != "Fixe"],
            key=lambda row: v14_engine._segment_sort_key(row, demands),
        )

        raw_capacity: dict[tuple[str, date], float] = {}
        fixed_used: dict[tuple[str, date], float] = {}
        flexible_used: dict[tuple[str, date], float] = {}
        rows: list[dict[str, Any]] = list(preserved)
        generation = datetime.now()
        sequence = 0

        def capacity(technician: str, day: date) -> float:
            key = (technician, day)
            if key not in raw_capacity:
                raw_capacity[key] = v13._availability_hours(repo, technician, day)
            return raw_capacity[key]

        # Les décisions manuelles/verrouillées ont la priorité absolue.
        # Les segments fixes utilisent ensuite la capacité standard restante. Si
        # elle est insuffisante, le reliquat est quand même placé et sera signalé
        # visuellement comme surcharge.
        for segment in fixed:
            tech = str(segment.get("Technicien") or "").strip()
            segment_id = str(segment.get("IDSegment") or "")
            remaining_hours = max(
                v13._number(segment.get("HeuresPrevues"))
                - locked_by_segment.get(segment_id, 0.0),
                0.0,
            )
            if remaining_hours <= 0:
                continue
            start, end = v13._segment_dates(segment)
            if not start or not end:
                continue

            residual: list[tuple[date, float]] = []
            raw_days: list[tuple[date, float]] = []
            cursor = start
            while cursor <= end:
                raw = capacity(tech, cursor)
                if raw > 0:
                    raw_days.append((cursor, raw))
                    room = max(raw - locked_used.get((tech, cursor), 0.0), 0.0)
                    if room > 0:
                        residual.append((cursor, room))
                cursor += timedelta(days=1)

            spread = v14_engine._spread_hours(remaining_hours, residual)
            placed = sum(spread.values())
            missing = max(remaining_hours - placed, 0.0)
            if missing > 0.001 and raw_days:
                overflow = v14_engine._spread_hours(missing, raw_days)
                for day, amount in overflow.items():
                    spread[day] = spread.get(day, 0.0) + amount

            competence = v14_engine.segment_competence(segment, demands)
            priority = v14_engine.segment_priority(segment, demands)
            for day, amount in spread.items():
                sequence += 1
                fixed_used[(tech, day)] = fixed_used.get((tech, day), 0.0) + amount
                rows.append(
                    _auto_payload(
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

        # Les segments flexibles ne prennent que la capacité réellement résiduelle.
        for segment in flexible:
            tech = str(segment.get("Technicien") or "").strip()
            segment_id = str(segment.get("IDSegment") or "")
            remaining_hours = max(
                v13._number(segment.get("HeuresPrevues"))
                - locked_by_segment.get(segment_id, 0.0),
                0.0,
            )
            if remaining_hours <= 0:
                continue
            start, end = v13._segment_dates(segment)
            if not start or not end:
                continue

            residual: list[tuple[date, float]] = []
            cursor = start
            while cursor <= end:
                available = max(
                    capacity(tech, cursor)
                    - locked_used.get((tech, cursor), 0.0)
                    - fixed_used.get((tech, cursor), 0.0)
                    - flexible_used.get((tech, cursor), 0.0),
                    0.0,
                )
                if available > 0:
                    residual.append((cursor, available))
                cursor += timedelta(days=1)

            spread = v14_engine._spread_hours(remaining_hours, residual)
            competence = v14_engine.segment_competence(segment, demands)
            priority = v14_engine.segment_priority(segment, demands)
            for day, amount in spread.items():
                sequence += 1
                flexible_used[(tech, day)] = flexible_used.get((tech, day), 0.0) + amount
                rows.append(
                    _auto_payload(
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
                0 if _truthy(row.get("Verrouillee")) else 1,
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
            "locked_allocations": len(preserved),
            "requested_hours": round(requested, 2),
            "allocated_hours": round(allocated, 2),
            "unallocated_hours": round(max(requested - allocated, 0.0), 2),
        }


def _allocation_header_map(repo: ExcelRepository) -> dict[str, int]:
    ensure_v15_sheets(repo)
    sheet = repo._book().sheets[v14_engine.ALLOCATION_SHEET]
    headers = _as_matrix(
        sheet.range((1, 1), (1, len(v14_engine.ALLOCATION_HEADERS))).value
    )[0]
    return {
        str(value).strip(): index + 1
        for index, value in enumerate(headers)
        if value not in (None, "")
    }


def _validate_manual_allocation(
    repo: ExcelRepository,
    segment: dict[str, Any],
    technician: str,
    day_value: Any,
    hours: float,
    hors_horaire: bool,
) -> date:
    day = _date_from_any(day_value)
    if not day:
        raise ValueError("La date du quart est requise.")
    if not technician:
        raise ValueError("Un technicien est requis pour un quart manuel.")
    if hours <= 0:
        raise ValueError("Les heures doivent être supérieures à zéro.")
    start, end = v13._segment_dates(segment)
    if start and day < start or end and day > end:
        raise ValueError("Le quart manuel doit demeurer dans la fenêtre du segment.")
    if v13._availability_hours(repo, technician, day) <= 0 and not hors_horaire:
        raise ValueError(
            "Le technicien n'est pas disponible selon son horaire standard cette journée. "
            "Coche « Hors horaire » pour autoriser explicitement ce quart."
        )
    return day


def create_manual_allocation(
    repo: ExcelRepository,
    segment_id: str,
    technician: str,
    day_value: Any,
    hours_value: Any,
    hors_horaire: bool = False,
    note: str = "",
) -> str:
    segment = next(
        (
            row
            for row in v13.segment_records(repo, include_cancelled=False)
            if str(row.get("IDSegment") or "") == str(segment_id)
        ),
        None,
    )
    if not segment:
        raise KeyError(f"Segment {segment_id} introuvable")
    hours = v13._number(hours_value)
    day = _validate_manual_allocation(
        repo, segment, technician.strip(), day_value, hours, hors_horaire
    )
    demands = v14_engine.demand_lookup(repo)
    generation = datetime.now()
    identifier = f"MAN-{generation.strftime('%Y%m%d%H%M%S%f')}"

    # Un segment correspond à une ressource. Affecter un quart manuel affecte donc
    # également le segment à cette ressource pour le reliquat automatique.
    if str(segment.get("Technicien") or "").strip() != technician.strip():
        v13.update_segment(
            repo,
            str(segment.get("IDSegment")),
            {"Technicien": technician.strip(), "Statut": "Planifié"},
        )
        segment = next(
            row
            for row in v13.segment_records(repo, include_cancelled=False)
            if str(row.get("IDSegment") or "") == str(segment_id)
        )

    payload = {
        "IDAllocation": identifier,
        "IDSegment": segment.get("IDSegment"),
        "NoDemande": segment.get("NoDemande"),
        "NumeroProjet": segment.get("NumeroProjet"),
        "NomProjet": segment.get("NomProjet"),
        "Technicien": technician.strip(),
        "Date": datetime.combine(day, datetime.min.time()),
        "Heures": round(hours, 2),
        "TypeAllocation": v14_engine.segment_plan_type(segment),
        "CompetenceRequise": v14_engine.segment_competence(segment, demands),
        "Priorite": v14_engine.segment_priority(segment, demands),
        "DateGeneration": generation,
        "Verrouillee": "Oui",
        "HorsHoraire": "Oui" if hors_horaire else "Non",
        "Note": note,
    }
    repo._append_dict_row(
        v14_engine.ALLOCATION_SHEET,
        v14_engine.ALLOCATION_HEADERS,
        payload,
        v14_engine.ALLOCATION_TABLE,
    )
    rebuild_allocations(repo)
    return identifier


def update_manual_allocation(
    repo: ExcelRepository,
    identifier: str,
    technician: str,
    day_value: Any,
    hours_value: Any,
    hors_horaire: bool = False,
    note: str = "",
) -> None:
    allocation = allocation_by_id(repo, identifier)
    if not allocation:
        raise KeyError(f"Allocation {identifier} introuvable")
    segment_id = str(allocation.get("IDSegment") or "")
    segment = next(
        (
            row
            for row in v13.segment_records(repo, include_cancelled=False)
            if str(row.get("IDSegment") or "") == segment_id
        ),
        None,
    )
    if not segment:
        raise KeyError(f"Segment {segment_id} introuvable")
    hours = v13._number(hours_value)
    day = _validate_manual_allocation(
        repo, segment, technician.strip(), day_value, hours, hors_horaire
    )

    if str(segment.get("Technicien") or "").strip() != technician.strip():
        v13.update_segment(
            repo,
            segment_id,
            {"Technicien": technician.strip(), "Statut": "Planifié"},
        )

    with repo._lock:
        sheet = repo._book().sheets[v14_engine.ALLOCATION_SHEET]
        header_map = _allocation_header_map(repo)
        excel_row = int(allocation.get("_row") or 0)
        updates = {
            "Technicien": technician.strip(),
            "Date": datetime.combine(day, datetime.min.time()),
            "Heures": round(hours, 2),
            "Verrouillee": "Oui",
            "HorsHoraire": "Oui" if hors_horaire else "Non",
            "Note": note,
        }
        for key, value in updates.items():
            col = header_map.get(key)
            if col:
                sheet.range((excel_row, col)).value = value
        repo.save()
    rebuild_allocations(repo)


def release_manual_allocation(repo: ExcelRepository, identifier: str) -> None:
    allocation = allocation_by_id(repo, identifier)
    if not allocation:
        return
    with repo._lock:
        sheet = repo._book().sheets[v14_engine.ALLOCATION_SHEET]
        header_map = _allocation_header_map(repo)
        col = header_map.get("Verrouillee")
        if col:
            sheet.range((int(allocation["_row"]), col)).value = "Non"
        repo.save()
    rebuild_allocations(repo)


def delete_manual_allocation(repo: ExcelRepository, identifier: str) -> None:
    allocation = allocation_by_id(repo, identifier)
    if not allocation:
        return
    with repo._lock:
        sheet = repo._book().sheets[v14_engine.ALLOCATION_SHEET]
        sheet.range(
            (int(allocation["_row"]), 1),
            (int(allocation["_row"]), len(v14_engine.ALLOCATION_HEADERS)),
        ).clear_contents()
        repo.save()
    rebuild_allocations(repo)


def weekly_allocation_load(repo: ExcelRepository, start: date) -> list[dict[str, Any]]:
    techs = {row["name"]: row for row in schedulable_technicians(repo)}
    end = start + timedelta(days=6)
    allocations = [
        row
        for row in allocation_records(repo)
        if row.get("Date") and start <= row["Date"] <= end
    ]
    result: list[dict[str, Any]] = []
    for name, info in techs.items():
        capacity = sum(
            v13._availability_hours(repo, name, start + timedelta(days=index))
            for index in range(7)
        )
        planned = sum(
            v13._number(row.get("Heures"))
            for row in allocations
            if str(row.get("Technicien") or "").strip() == name
        )
        overtime = sum(
            v13._number(row.get("Heures"))
            for row in allocations
            if str(row.get("Technicien") or "").strip() == name
            and _truthy(row.get("HorsHoraire"))
        )
        pct = round(planned / capacity * 100, 0) if capacity else None
        result.append(
            {
                "name": name,
                "planned": round(planned, 1),
                "weekly_capacity": round(capacity, 1),
                "overtime": round(overtime, 1),
                "available": round(max(capacity - planned, 0.0), 1),
                "pct": pct,
                "team": info.get("team") or "",
                "description": info.get("description") or "",
            }
        )
    result.sort(key=lambda row: (-(row["pct"] or -1), row["name"]))
    return result
