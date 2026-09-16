from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time

from .read_models import DemandPeriodReadModel, DemandReadModel, SegmentReadModel


@dataclass(frozen=True, slots=True)
class ProjectReadModel:
    id: str
    number: str
    name: str
    client: str | None = None
    project_manager: str | None = None
    status: str = "active"
    active: bool = True
    erp_external_id: str | None = None


@dataclass(frozen=True, slots=True)
class WorkPackageReadModel:
    id: str
    reference: str
    project_number: str
    code: str | None
    name: str
    description: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    planned_hours: float | None = None
    status: str = "planned"


@dataclass(frozen=True, slots=True)
class ResourceReadModel:
    id: str
    name: str
    email: str | None = None
    resource_class: str | None = None
    competencies: str | None = None
    note: str | None = None
    active: bool = True
    sort_order: int = 0
    external_id: str | None = None


@dataclass(frozen=True, slots=True)
class ResourceAvailabilityRuleReadModel:
    id: str
    availability_type: str
    resource_id: str | None = None
    resource_name: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    weekdays: str | None = None
    start_time: time | None = None
    end_time: time | None = None
    note: str | None = None
    active: bool = True


@dataclass(frozen=True, slots=True)
class DemandHistoryReadModel:
    demand_number: str
    action: str
    occurred_at: datetime
    previous_status: str | None = None
    status: str | None = None
    comment: str | None = None
    details: str | None = None
    actor_name: str | None = None


@dataclass(frozen=True, slots=True)
class PlanningHistoryReadModel:
    entity_type: str
    entity_reference: str
    action: str
    occurred_at: datetime
    parent_reference: str | None = None
    details: str | None = None
    actor_name: str | None = None


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
    demand_number: str | None = None
    project_number: str | None = None
    project_name: str | None = None
    project_manager: str | None = None
    requester: str | None = None
    emergency_override_active: bool = False


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
class MediumTermCapacityBucketReadModel:
    """One backend-authoritative weekly capacity bucket.

    ``resource_class=None`` is the all-resources total. Replacement proposals are
    reported separately and are never added to ``exposure_hours``.
    """

    week_start: date
    week_end: date
    resource_class: str | None
    resource_count: int
    capacity_hours: float
    firm_hours: float
    current_potential_hours: float
    submitted_hours: float
    replacement_proposal_hours: float
    replacement_delta_hours: float
    exposure_hours: float
    firm_residual_hours: float
    residual_hours: float
    utilization_pct: float | None
    state: str


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
    capacity_buckets: tuple[MediumTermCapacityBucketReadModel, ...] = ()
    firm_hours: float = 0.0
    potential_hours: float = 0.0
    replacement_proposal_hours: float = 0.0