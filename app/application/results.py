from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


class ApplicationResult:
    """Transport-neutral result contract exposed by the application facade."""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class PlanningResult(ApplicationResult):
    segments: int = 0
    allocations: int = 0
    locked_allocations: int = 0
    requested_hours: float = 0.0
    allocated_hours: float = 0.0
    overtime_hours: float = 0.0
    unallocated_hours: float = 0.0
    engine: str = ""

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any] | None) -> "PlanningResult":
        source = dict(values or {})
        return cls(
            segments=_integer(source.get("segments")),
            allocations=_integer(source.get("allocations")),
            locked_allocations=_integer(source.get("locked_allocations")),
            requested_hours=_number(source.get("requested_hours")),
            allocated_hours=_number(source.get("allocated_hours")),
            overtime_hours=_number(source.get("overtime_hours")),
            unallocated_hours=_number(source.get("unallocated_hours")),
            engine=str(source.get("planning_engine") or source.get("engine") or "").strip(),
        )


@dataclass(frozen=True, slots=True)
class WorkPackageMutationResult(ApplicationResult):
    reference: str
    action: str


@dataclass(frozen=True, slots=True)
class DemandMutationResult(ApplicationResult):
    demand_number: str
    status: str | None = None
    reapproval_required: bool = False
    planning: PlanningResult | None = None


@dataclass(frozen=True, slots=True)
class DemandPeriodsMutationResult(ApplicationResult):
    demand_number: str
    period_count: int
    status: str | None = None
    reapproval_required: bool = False


@dataclass(frozen=True, slots=True)
class DemandAlternativeSelectionResult(ApplicationResult):
    demand_number: str
    alternative_group: str
    period_id: str
    planning: PlanningResult | None = None
    operational_version: int | None = None


@dataclass(frozen=True, slots=True)
class DemandOperationalConfirmationResult(ApplicationResult):
    demand_number: str
    confirmation: str
    operational_version: int
    planning: PlanningResult | None = None


@dataclass(frozen=True, slots=True)
class SegmentMutationResult(ApplicationResult):
    segment_id: str
    action: str
    planning: PlanningResult
    technician: str | None = None


@dataclass(frozen=True, slots=True)
class AllocationMutationResult(ApplicationResult):
    allocation_id: str
    action: str


@dataclass(frozen=True, slots=True)
class QuickShiftCreatedResult(ApplicationResult):
    segment_id: str
    allocation_id: str


@dataclass(frozen=True, slots=True)
class CompositeAllocationMutationResult(ApplicationResult):
    operation: str
    source_allocation_id: str
    target_allocation_id: str
    source_shift_id: str
    target_shift_id: str
    segment_id: str
    requirement_id: str
    source_hours: float
    target_hours: float
    planned_hours: float
    locked_hours: float
    excess_hours: float
    planning_version: int
    approval_revision_id: str | None = None
    operational_version: int | None = None
    auto_source_converted: bool = False

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "CompositeAllocationMutationResult":
        source = dict(values)
        operational = source.get("operational_version")
        return cls(
            operation=str(source.get("operation") or ""),
            source_allocation_id=str(source.get("source_allocation_id") or ""),
            target_allocation_id=str(source.get("target_allocation_id") or ""),
            source_shift_id=str(source.get("source_shift_id") or ""),
            target_shift_id=str(source.get("target_shift_id") or ""),
            segment_id=str(source.get("segment_id") or ""),
            requirement_id=str(source.get("requirement_id") or ""),
            source_hours=_number(source.get("source_hours")),
            target_hours=_number(source.get("target_hours")),
            planned_hours=_number(source.get("planned_hours")),
            locked_hours=_number(source.get("locked_hours")),
            excess_hours=_number(source.get("excess_hours")),
            planning_version=_integer(source.get("planning_version")),
            approval_revision_id=(
                str(source.get("approval_revision_id"))
                if source.get("approval_revision_id") is not None
                else None
            ),
            operational_version=(
                int(operational) if operational is not None else None
            ),
            auto_source_converted=bool(source.get("auto_source_converted")),
        )
