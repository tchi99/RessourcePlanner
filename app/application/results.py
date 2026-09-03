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
