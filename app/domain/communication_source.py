from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Mapping, Sequence

from .communication_planning import WeeklyAssignment


TRUE_VALUES = {"oui", "true", "1", "x", "yes", "actif", "active", "verrouille", "verrouillée"}
MISSING_MARKERS = {"requis", "required"}


def _as_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text[:19], fmt).date()
        except ValueError:
            continue
    return None


def _number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in TRUE_VALUES


def _lookup(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, Mapping[str, Any]]:
    return {
        str(row.get(key) or "").strip(): row
        for row in rows
        if str(row.get(key) or "").strip()
    }


def _is_missing_placeholder(row: Mapping[str, Any]) -> bool:
    outside = str(row.get("HorsHoraire") or "").strip().lower()
    allocation_type = str(row.get("TypeAllocation") or "").strip().lower()
    return outside in MISSING_MARKERS or "hors horaire requis" in allocation_type


def weekly_assignments_from_records(
    allocation_rows: Sequence[Mapping[str, Any]],
    segment_rows: Sequence[Mapping[str, Any]],
    demand_rows: Sequence[Mapping[str, Any]],
    week_start: date,
) -> list[WeeklyAssignment]:
    """Build communication assignments from an in-memory planning snapshot.

    Missing/outside-schedule proposals are deliberately excluded: a communication must
    only describe work that is actually allocated. Multiple allocation rows for the
    same segment/resource/day are aggregated into a single readable line.
    """
    week_end = week_start + timedelta(days=6)
    segments = _lookup(segment_rows, "IDSegment")
    demands = _lookup(demand_rows, "NoDemande")

    grouped_hours: dict[tuple[object, ...], float] = defaultdict(float)
    grouped_types: dict[tuple[object, ...], set[str]] = defaultdict(set)

    for allocation in allocation_rows:
        if _is_missing_placeholder(allocation):
            continue
        day = _as_date(allocation.get("Date"))
        if not day or day < week_start or day > week_end:
            continue
        hours = _number(allocation.get("Heures"))
        if hours <= 0:
            continue

        segment_id = str(allocation.get("IDSegment") or "").strip()
        segment = segments.get(segment_id, {})
        if str(segment.get("Statut") or "").strip().lower() in {"annulé", "annule", "terminé", "termine"}:
            continue

        resource_id = str(allocation.get("Technicien") or segment.get("Technicien") or "").strip()
        if not resource_id:
            continue
        resource_name = str(
            allocation.get("NomRessource")
            or segment.get("NomRessource")
            or resource_id
        ).strip()

        request_id = str(allocation.get("NoDemande") or segment.get("NoDemande") or "").strip()
        demand = demands.get(request_id, {})
        manager_id = str(
            allocation.get("ChargeProjet")
            or segment.get("ChargeProjet")
            or demand.get("ChargeProjet")
            or ""
        ).strip()
        project_number = str(
            allocation.get("NumeroProjet")
            or segment.get("NumeroProjet")
            or demand.get("NumeroProjet")
            or ""
        ).strip()
        project_name = str(
            allocation.get("NomProjet")
            or segment.get("NomProjet")
            or demand.get("NomProjet")
            or ""
        ).strip()
        confirmation = str(
            allocation.get("Confirmation")
            or segment.get("Confirmation")
            or segment.get("StatutConfirmation")
            or demand.get("Confirmation")
            or "Confirmée"
        ).strip()
        outside_schedule = _truthy(allocation.get("HorsHoraire"))

        key = (
            segment_id,
            resource_id,
            resource_name,
            manager_id,
            project_number,
            project_name,
            day,
            outside_schedule,
            confirmation,
        )
        grouped_hours[key] += hours
        allocation_type = str(allocation.get("TypeAllocation") or "Planifié").strip() or "Planifié"
        grouped_types[key].add(allocation_type)

    result: list[WeeklyAssignment] = []
    for key, hours in grouped_hours.items():
        (
            segment_id,
            resource_id,
            resource_name,
            manager_id,
            project_number,
            project_name,
            day,
            outside_schedule,
            confirmation,
        ) = key
        types = grouped_types[key]
        allocation_type = next(iter(types)) if len(types) == 1 else "Planifié"
        result.append(
            WeeklyAssignment(
                segment_id=str(segment_id),
                resource_id=str(resource_id),
                resource_name=str(resource_name),
                project_manager_id=str(manager_id),
                project_number=str(project_number),
                project_name=str(project_name),
                day=day,  # type: ignore[arg-type]
                hours=round(hours, 2),
                allocation_type=allocation_type,
                outside_schedule=bool(outside_schedule),
                confirmation=str(confirmation),
            )
        )

    result.sort(
        key=lambda row: (
            row.day,
            row.resource_name.lower(),
            row.project_number.lower(),
            row.segment_id,
        )
    )
    return result


def technician_ids_for_weekly_communication(
    technician_rows: Sequence[Mapping[str, Any]],
) -> list[str]:
    """Return the explicit technician audience, including people with no assignment."""
    ids = {
        str(row.get("name") or row.get("Technicien") or "").strip()
        for row in technician_rows
    }
    return sorted(value for value in ids if value)
