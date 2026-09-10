from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .read_models import DemandPeriodReadModel, DemandReadModel, SegmentReadModel


@dataclass(frozen=True, slots=True)
class ProjectReadModel:
    id: str
    number: str
    name: str
    client: str | None = None
    project_manager: str | None = None
    status: str = "active"
    erp_external_id: str | None = None


@dataclass(frozen=True, slots=True)
class ResourceReadModel:
    id: str
    name: str
    resource_class: str | None = None
    competencies: str | None = None
    note: str | None = None
    active: bool = True
    sort_order: int = 0
    external_id: str | None = None


@dataclass(frozen=True, slots=True)
class ShiftReadModel:
    allocation_id: str
    segment_id: str
    resource_id: str
    resource_name: str
    work_date: date
    hours: float
    allocation_type: str | None = None
    source: str = "AUTO"
    locked: bool = False
    outside_standard_hours: bool = False
    confirmation: str | None = None
    confirmation_override: str | None = None
    load_kind: str = "FIRM"
    note: str | None = None


@dataclass(frozen=True, slots=True)
class PendingDemandLoadReadModel:
    """Read-only workload proposed by a submitted, not-yet-approved request.

    ``mode=ADDITIVE`` is concurrent potential load and may be added to the current
    capacity exposure. ``mode=REPLACEMENT`` is a scenario that would replace the
    currently approved plan and is intentionally kept out of additive totals.
    """

    demand_number: str
    project_number: str | None
    project_name: str | None
    start_date: date
    end_date: date
    projected_hours: float | None
    window_hours: float
    mode: str
    load_kind: str = "POTENTIAL"
    current_plan_hours: float = 0.0
    delta_hours: float | None = None
    resource_count: int = 1
    required_competencies: str | None = None
    proposed_resource: str | None = None
    work_package_ref: str | None = None
    confirmation: str | None = None
    periods: tuple[DemandPeriodReadModel, ...] = ()


@dataclass(frozen=True, slots=True)
class PlanningSnapshotReadModel:
    """Canonical, transaction-coherent planning window exposed to web clients."""

    start: date
    end: date
    resources: tuple[ResourceReadModel, ...]
    demands: tuple[DemandReadModel, ...]
    segments: tuple[SegmentReadModel, ...]
    shifts: tuple[ShiftReadModel, ...]
    pending_loads: tuple[PendingDemandLoadReadModel, ...] = ()
    firm_hours: float = 0.0
    potential_hours: float = 0.0
    replacement_proposal_hours: float = 0.0
