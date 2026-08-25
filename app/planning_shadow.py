from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Sequence

from .application.repository_ports import PlanningReadRepositoryPort
from .domain.availability_rules import (
    availability_hours_for_day,
    has_standard_schedule,
    outside_schedule_eligible_for_day,
)
from .domain.plan_comparison import (
    AllocationProjection,
    PlanComparison,
    compare_allocation_plans,
)
from .domain.plan_diagnostics import (
    SegmentAllocationBoundsSummary,
    summarize_segment_allocation_bounds,
)
from .domain.planning_engine import (
    LockedAllocationInput,
    PlanResult,
    SegmentInput,
    build_allocation_plan,
)
from .domain.planning_snapshot import PlanningSnapshot
from .excel_repository import _date_from_any


PRIORITY_ORDER = {"Urgent": 0, "Élevée": 1, "Normale": 2, "Basse": 3}
PLAN_TYPES = {"Flexible", "Fixe"}
TRUE_VALUES = {"oui", "yes", "true", "1", "x", "verrouille", "verrouillée"}
SEGMENT_OVERTIME_FIELD = "HorsHoraireAutorise"


@dataclass(frozen=True)
class ShadowPlanReport:
    """Comparison between persisted allocations and the pure engine."""

    comparison: PlanComparison
    shadow_result: PlanResult
    allocation_bounds: SegmentAllocationBoundsSummary
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


def build_planning_snapshot(reader: PlanningReadRepositoryPort) -> PlanningSnapshot:
    """Capture one immutable calculation snapshot through the persistence port."""

    return reader.capture()


def _demand_lookup(rows: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
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
    technician_rows: Sequence[dict[str, Any]],
    availability_rows: Sequence[dict[str, Any]],
) -> set[str]:
    configured = {str(row.get("name") or "").strip() for row in technician_rows}
    return {
        resource_id
        for resource_id in configured
        if resource_id and has_standard_schedule(availability_rows, resource_id)
    }


def _segment_inputs(
    segment_rows: Sequence[dict[str, Any]],
    demand_rows: Sequence[dict[str, Any]],
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
                overtime_allowed=_truthy(row.get(SEGMENT_OVERTIME_FIELD)),
            )
        )

    return inputs, tuple(sorted(set(unsupported)))


def _locked_inputs(allocation_rows: Sequence[dict[str, Any]]) -> list[LockedAllocationInput]:
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
    availability_rows: Sequence[dict[str, Any]],
    segments: Sequence[SegmentInput],
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


def _outside_schedule_eligibility_snapshot(
    availability_rows: Sequence[dict[str, Any]],
    segments: Sequence[SegmentInput],
) -> dict[tuple[str, date], bool]:
    result: dict[tuple[str, date], bool] = {}
    for segment in segments:
        cursor = segment.start
        while cursor <= segment.end:
            key = (segment.resource_id, cursor)
            if key not in result:
                result[key] = outside_schedule_eligible_for_day(
                    availability_rows,
                    segment.resource_id,
                    cursor,
                )
            cursor += timedelta(days=1)
    return result


def _legacy_projection(
    allocation_rows: Sequence[dict[str, Any]],
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


def build_shadow_report_from_snapshot(snapshot: PlanningSnapshot) -> ShadowPlanReport:
    """Calculate the pure plan and comparison entirely from one captured snapshot."""
    schedulable = _schedulable_resource_ids(snapshot.technicians, snapshot.availability)
    segments, unsupported = _segment_inputs(snapshot.segments, snapshot.demands, schedulable)
    locked = _locked_inputs(snapshot.allocations)
    capacities = _capacity_snapshot(snapshot.availability, segments)
    outside_schedule_eligible = _outside_schedule_eligibility_snapshot(
        snapshot.availability,
        segments,
    )
    shadow_result = build_allocation_plan(
        segments,
        locked,
        capacities,
        outside_schedule_eligible_by_resource_day=outside_schedule_eligible,
    )
    included_ids = {segment.segment_id for segment in segments}
    comparison = compare_allocation_plans(
        _legacy_projection(snapshot.allocations, included_ids),
        _shadow_projection(shadow_result),
    )
    allocation_bounds = summarize_segment_allocation_bounds(
        segments,
        shadow_result.allocations,
    )
    return ShadowPlanReport(
        comparison=comparison,
        shadow_result=shadow_result,
        allocation_bounds=allocation_bounds,
        unsupported_segment_ids=unsupported,
    )


def build_shadow_report_from_repository(
    reader: PlanningReadRepositoryPort,
) -> ShadowPlanReport:
    """Capture once through the repository port, then calculate entirely in memory."""

    return build_shadow_report_from_snapshot(build_planning_snapshot(reader))


def build_shadow_report(repo: Any) -> ShadowPlanReport:
    """Backward-compatible Excel adapter for diagnostics/tools during V1 migration."""

    from .infrastructure.excel.planning_repository import ExcelPlanningReadRepository

    return build_shadow_report_from_repository(ExcelPlanningReadRepository(repo))
