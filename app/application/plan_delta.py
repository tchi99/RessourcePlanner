from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Mapping


@dataclass(frozen=True, slots=True)
class DemandPlanDeltaDiagnosticReadModel:
    code: str
    message: str
    requirement_id: str | None = None
    spec_key: tuple[str, ...] | None = None
    shift_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DemandApprovalStateReadModel:
    demand_number: str
    candidate_request_version: int
    approval_reference_status: str | None
    active_revision_id: str | None = None
    previous_revision_id: str | None = None
    approved_request_version: int | None = None
    approved_at: datetime | None = None
    approved_by_name: str | None = None
    authorization_fingerprint: str | None = None
    candidate_authorization_fingerprint: str | None = None
    candidate_matches_approved: bool | None = None
    payload_format_version: int | None = None
    operational_version: int | None = None
    envelope_decision: str | None = None
    envelope_reason: str | None = None
    envelope_changes: tuple[Mapping[str, object], ...] = ()
    active_selections: Mapping[str, str] = field(default_factory=dict)
    active_confirmations: Mapping[str, str] = field(default_factory=dict)
    active_budget_overrides: Mapping[str, float] = field(default_factory=dict)
    active_requirement_count: int = 0
    active_planned_hours: float = 0.0
    active_asset_requirement_count: int = 0
    active_asset_usage_hours: float = 0.0
    active_asset_unbudgeted_requirement_count: int = 0
    active_approved_entry_keys: tuple[str, ...] = ()
    active_matches_approved_revision: bool | None = None
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DemandPlanDeltaItemReadModel:
    change: str
    segment_id: str
    current_resource_name: str | None = None
    proposed_resource_name: str | None = None
    current_resource_id: str | None = None
    proposed_resource_id: str | None = None
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
class DemandAssetPlanDeltaItemReadModel:
    change: str
    approved_entry_key: str
    slot_index: int
    current_requirement_id: str | None = None
    current_asset_type_id: str | None = None
    proposed_asset_type_id: str | None = None
    current_start_date: date | None = None
    current_end_date: date | None = None
    proposed_start_date: date | None = None
    proposed_end_date: date | None = None
    current_usage_hours: float | None = None
    proposed_usage_hours: float | None = None
    current_asset_id: str | None = None
    proposed_asset_id: str | None = None
    allocation_preserved: bool = False
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
    asset_add_count: int = 0
    asset_modify_count: int = 0
    asset_cancel_count: int = 0
    asset_items: tuple[DemandAssetPlanDeltaItemReadModel, ...] = ()
    approval_reference_status: str | None = None
    active_revision_id: str | None = None
    approved_request_version: int | None = None
    authorization_fingerprint: str | None = None
    candidate_authorization_fingerprint: str | None = None
    operational_version: int | None = None
    envelope_decision: str | None = None
    envelope_reason: str | None = None
    diagnostics: tuple[DemandPlanDeltaDiagnosticReadModel, ...] = ()
