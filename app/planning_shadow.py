from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from .domain.availability_rules import availability_hours_for_day, has_standard_schedule
from .domain.plan_comparison import (
    AllocationProjection,
    PlanComparison,
    compare_allocation_plans,
)
from .domain.planning_engine import (
    LockedAllocationInput,
    PlanResult,
    SegmentInput,
    build_allocation_plan,
)
from .excel_repository import ExcelRepository, _date_from_any


PRIORITY_ORDER = {"Urgent": 0, "Élevée": 1, "Normale": 2, "Basse": 3}
PLAN_TYPES = {"Flexible", "Fixe"}
TRUE_VALUES = {"oui", "yes", "true", "1", "x", "verrouille", "verrouillée"}


@dataclass(frozen=True)
class ShadowPlanReport:
    """Comparison between persisted legacy allocations and the pure engine."""

    comparison: PlanComparison
    shadow_result: PlanResult
    unsupported_segment_ids: tuple[str, ...]


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


def _records(repo: ExcelRepository, sheet: str, expected_header: str) -> list[dict[str, Any]]:
    try:
        return repo._sheet_as_records(sheet, expected_header)
    except Exception:
        return []


def _demand_lookup(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("NoDemande") or ""): row
        for row in rows
        if row.get("NoDemande")
    }


def _priority_rank(row: dict[str, Any], demands: dict[str, dict[str, Any]]) -> int:
    priority = str(row.get("Priorite") or "").strip()
    if not priority:
        demand = demands.get(str(row.get("NoDemande") or ""), {})
        priority = str(demand.get("Priorite") or "Normale")
    return PRIORITY_ORDER.get(priority, 2)


def _plan_type(row: dict[str, Any]) -> str:
    value = str(row.get("TypePlanification") or "Flexible").strip()
    return value if value in PLAN_TYPES else "Flexible"


def _schedulable_resource_ids(
    repo: ExcelRepository,
    availability_rows: list[dict[str, Any]],
) -> set[str]:
    configured = {str(row.get("name") or "").strip() for row in repo.technicians()}
    return {
        resource_id
        for resource_id in configured
        if resource_id and has_standard_schedule(availability_rows, resource_id)
    }


def _segment_inputs(
    segment_rows: list[dict[str, Any]],
    demand_rows: list[dict[str, Any]],
    schedulable: set[str],
) -> tuple[list[SegmentInput], tuple[str, ...]]:
    demands = _demand_lookup(demand_rows)
    inputs: list[SegmentInput] = []
    unsupported: list[str] = []

    for row in segment_rows:
        status = str(row.get("Statut") or "")
        resource_id = str(row.get("Technicien") or "").strip()
        hours = _number(row.get("HeuresPrevues"))
        if status in {"Annulé", "Terminé"} or resource_id not in schedulable or hours <= 0:
            continue

        segment_id = str(row.get("IDSegment") or "").strip()
        start = _date_from_any(row.get("DateDebut"))
        end = _date_from_any(row.get("DateFin")) or start
        if not segment_id or not start or not end:
            if segment_id:
                unsupported.append(segment_id)
            continue

        inputs.append(
            SegmentInput(
                segment_id=segment_id,
                resource_id=resource_id,
                start=start,
                end=end,
                hours=hours,
                plan_type=_plan_type(row),
                priority_rank=_priority_rank(row, demands),
                created_order=str(row.get("DateCreation") or ""),
            )
        )

    return inputs, tuple(sorted(set(unsupported)))


def _locked_inputs(allocation_rows: list[dict[str, Any]]) -> list[LockedAllocationInput]:
    result: list[LockedAllocationInput] = []
    for row in allocation_rows:
        if not _truthy(row.get("Verrouillee")):
            continue
        day = _date_from_any(row.get("Date"))
        resource_id = str(row.get("Technicien") or "").strip()
        segment_id = str(row.get("IDSegment") or "").strip()
        hours = _number(row.get("Heures"))
        if not day or not resource_id or not segment_id or hours <= 0:
            continue
        result.append(
            LockedAllocationInput(
                segment_id=segment_id,
                resource_id=resource_id,
                day=day,
                hours=hours,
                outside_schedule=_truthy(row.get("HorsHoraire")),
            )
        )
    return result


def _capacity_snapshot(
    availability_rows: list[dict[str, Any]],
    segments: list[SegmentInput],
) -> dict[tuple[str, date], float]:
    """Evaluate each resource/day once from one in-memory availability snapshot."""
    result: dict[tuple[str, date], float] = {}
    for segment in segments:
        cursor = segment.start
        while cursor <= segment.end:
            key = (segment.resource_id, cursor)
            if key not in result:
                result[key] = availability_hours_for_day(
                    availability_rows,
                    segment.resource_id,
                    cursor,
                )
            cursor += timedelta(days=1)
    return result


def _legacy_projection(
    allocation_rows: list[dict[str, Any]],
    included_segment_ids: set[str],
) -> list[AllocationProjection]:
    result: list[AllocationProjection] = []
    for row in allocation_rows:
        segment_id = str(row.get("IDSegment") or "").strip()
        if segment_id not in included_segment_ids:
            continue
        day = _date_from_any(row.get("Date"))
        resource_id = str(row.get("Technicien") or "").strip()
        hours = _number(row.get("Heures"))
        if not day or not resource_id or hours <= 0:
            continue
        locked = _truthy(row.get("Verrouillee"))
        result.append(
            AllocationProjection(
                segment_id=segment_id,
                resource_id=resource_id,
                day=day,
                hours=hours,
                allocation_type="Locked" if locked else str(row.get("TypeAllocation") or ""),
                locked=locked,
                outside_schedule=_truthy(row.get("HorsHoraire")),
            )
        )
    return result


def _shadow_projection(result: PlanResult) -> list[AllocationProjection]:
    return [
        AllocationProjection(
            segment_id=row.segment_id,
            resource_id=row.resource_id,
            day=row.day,
            hours=row.hours,
            allocation_type=row.allocation_type,
            locked=row.locked,
            outside_schedule=row.outside_schedule,
        )
        for row in result.allocations
    ]


def build_shadow_report(repo: ExcelRepository) -> ShadowPlanReport:
    """Compare persisted V1.5 allocations to the pure engine without rebuilding them.

    The adapter takes one snapshot of each relevant worksheet, computes availability
    in memory, and never calls a repository write/save or the historical rebuild.
    If the repository is not connected yet, its normal connection routine may still
    perform the application's existing schema initialization before these reads.
    """
    with repo._lock:
        segment_rows = _records(repo, "SegmentsMO", "IDSegment")
        allocation_rows = _records(repo, "AllocationsMO", "IDAllocation")
        demand_rows = _records(repo, "DemandesMO", "NoDemande")
        availability_rows = _records(repo, "Disponibilites", "ID")
        schedulable = _schedulable_resource_ids(repo, availability_rows)

    segments, unsupported = _segment_inputs(segment_rows, demand_rows, schedulable)
    locked = _locked_inputs(allocation_rows)
    capacities = _capacity_snapshot(availability_rows, segments)
    shadow_result = build_allocation_plan(segments, locked, capacities)
    included_ids = {segment.segment_id for segment in segments}
    comparison = compare_allocation_plans(
        _legacy_projection(allocation_rows, included_ids),
        _shadow_projection(shadow_result),
    )
    return ShadowPlanReport(
        comparison=comparison,
        shadow_result=shadow_result,
        unsupported_segment_ids=unsupported,
    )
