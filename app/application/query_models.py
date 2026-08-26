from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .read_models import DemandReadModel, SegmentReadModel


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
    note: str | None = None


@dataclass(frozen=True, slots=True)
class PlanningSnapshotReadModel:
    """Canonical, transaction-coherent planning window exposed to web clients."""

    start: date
    end: date
    resources: tuple[ResourceReadModel, ...]
    demands: tuple[DemandReadModel, ...]
    segments: tuple[SegmentReadModel, ...]
    shifts: tuple[ShiftReadModel, ...]
