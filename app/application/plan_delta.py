from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class DemandPlanDeltaItemReadModel:
    change: str
    segment_id: str
    current_resource_name: str | None = None
    proposed_resource_name: str | None = None
    current_date: date | None = None
    proposed_date: date | None = None
    current_hours: float = 0.0
    proposed_hours: float = 0.0
    current_allocation_type: str | None = None
    proposed_allocation_type: str | None = None
    current_outside_standard_hours: bool = False
    proposed_outside_standard_hours: bool = False
    locked: bool = False


@dataclass(frozen=True, slots=True)
class DemandPlanDeltaReadModel:
    demand_number: str
    available: bool
    reason: str | None
    has_changes: bool
    add_count: int = 0
    modify_count: int = 0
    move_count: int = 0
    cancel_count: int = 0
    current_hours: float = 0.0
    proposed_hours: float = 0.0
    net_hours: float = 0.0
    items: tuple[DemandPlanDeltaItemReadModel, ...] = ()
