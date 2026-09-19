from __future__ import annotations

from datetime import date, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


AvailabilityType = Literal["Horaire standard", "Vacances", "Jour férié"]
OverallocationPolicy = Literal["KEEP_EXCEPTION", "INCREASE_PLANNED"]
LoadProfile = Literal["UNIFORM", "FRONT_LOADED", "BACK_LOADED", "BELL"]


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CompetencyCreateRequest(StrictRequest):
    name: str = Field(min_length=1)
    description: str | None = None
    active: bool = True
    sort_order: int = Field(default=0, ge=0)


class CompetencyUpdateRequest(StrictRequest):
    name: str | None = None
    description: str | None = None
    active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0)

    @field_validator("name", "active", "sort_order", mode="before")
    @classmethod
    def reject_null_required_competency_fields(cls, value: object) -> object:
        if value is None:
            raise ValueError("Ce champ ne peut pas être null; omets-le pour ne pas le modifier.")
        return value


class ResourceCreateRequest(StrictRequest):
    name: str = Field(min_length=1)
    email: str | None = None
    resource_class: str | None = None
    competencies: str | None = None
    competency_ids: list[str] | None = None
    note: str | None = None
    active: bool = True
    sort_order: int = Field(default=0, ge=0)
    external_id: str | None = None


class ResourceUpdateRequest(StrictRequest):
    name: str | None = None
    email: str | None = None
    resource_class: str | None = None
    competencies: str | None = None
    competency_ids: list[str] | None = None
    note: str | None = None
    active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0)
    external_id: str | None = None

    @field_validator("active", "sort_order", mode="before")
    @classmethod
    def reject_null_non_nullable_fields(cls, value: object) -> object:
        if value is None:
            raise ValueError("Ce champ ne peut pas être null; omets-le pour ne pas le modifier.")
        return value


class AvailabilityRuleCreateRequest(StrictRequest):
    availability_type: AvailabilityType
    resource_id: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    weekdays: str | None = None
    start_time: time | None = None
    end_time: time | None = None
    note: str | None = None
    active: bool = True


class AvailabilityRuleUpdateRequest(StrictRequest):
    availability_type: AvailabilityType | None = None
    resource_id: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    weekdays: str | None = None
    start_time: time | None = None
    end_time: time | None = None
    note: str | None = None
    active: bool | None = None

    @field_validator("availability_type", "active", mode="before")
    @classmethod
    def reject_null_required_patch_fields(cls, value: object) -> object:
        if value is None:
            raise ValueError("Ce champ ne peut pas être null; omets-le pour ne pas le modifier.")
        return value


class WorkPackageCreateRequest(StrictRequest):
    project_number: str = Field(min_length=1)
    name: str = Field(min_length=1)
    code: str | None = None
    description: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    planned_hours: float | None = Field(default=None, ge=0)
    status: str = Field(default="planned", min_length=1)


class WorkPackageUpdateRequest(StrictRequest):
    project_number: str | None = None
    code: str | None = None
    name: str | None = None
    description: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    planned_hours: float | None = Field(default=None, ge=0)
    status: str | None = None


class DemandCreateRequest(StrictRequest):
    project_number: str
    desired_start: date
    submit: bool = False
    project_name: str = ""
    client: str = ""
    requester: str | None = None
    work_package_ref: str | None = None
    task_code: str | None = None
    request_type: str = "Projet"
    priority: str = "Normale"
    confirmation: str = "Confirmée"
    desired_end: date | None = None
    description: str = ""
    site_client: str = ""
    location: str = ""
    resource_count: int = Field(default=1, ge=1)
    required_competencies: str | None = None
    required_competency_ids: list[str] | None = None
    estimated_hours: float | None = Field(default=None, ge=0)
    estimated_days: int | None = Field(default=None, ge=1)
    proposed_technician: str | None = None


class DemandUpdateRequest(StrictRequest):
    project_number: str | None = None
    project_name: str | None = None
    client: str | None = None
    requester: str | None = None
    work_package_ref: str | None = None
    task_code: str | None = None
    request_type: str | None = None
    priority: str | None = None
    confirmation: str | None = None
    desired_start: date | None = None
    desired_end: date | None = None
    description: str | None = None
    site_client: str | None = None
    location: str | None = None
    resource_count: int | None = Field(default=None, ge=1)
    required_competencies: str | None = None
    required_competency_ids: list[str] | None = None
    estimated_hours: float | None = Field(default=None, ge=0)
    estimated_days: int | None = Field(default=None, ge=1)
    proposed_technician: str | None = None
    comment: str = "Demande modifiée via API"


class DemandPeriodRequest(StrictRequest):
    period_id: str = Field(min_length=1)
    start_date: date
    end_date: date
    hours: float = Field(gt=0)
    kind: Literal["CUMULATIVE", "ALTERNATIVE"] = "CUMULATIVE"
    alternative_group: str | None = None
    confirmation: str = "Tentative"
    proposed_resource: str | None = None
    resource_count: int = Field(default=1, ge=1)
    desired_active_days: int | None = Field(default=None, ge=1)
    note: str = ""


class DemandPeriodsReplaceRequest(StrictRequest):
    periods: list[DemandPeriodRequest]


class DemandAlternativeSelectionRequest(StrictRequest):
    period_id: str = Field(min_length=1)


class OptionalCommentRequest(StrictRequest):
    comment: str = ""


class RequiredCommentRequest(StrictRequest):
    comment: str = Field(min_length=1)


class SegmentCreateRequest(StrictRequest):
    demand_number: str
    start_date: date
    end_date: date
    planned_hours: float = Field(gt=0)
    project_number: str | None = None
    project_name: str | None = None
    technician: str | None = None
    status: str = "À assigner"
    description: str = ""
    source_effort_id: str | None = None
    required_competency: str | None = None
    required_competency_id: str | None = None
    planning_type: str = "Flexible"
    priority: str = "Normale"
    outside_standard_hours: bool = False
    confirmation: str | None = None
    load_profile: LoadProfile = "UNIFORM"


class SegmentUpdateRequest(StrictRequest):
    demand_number: str | None = None
    project_number: str | None = None
    project_name: str | None = None
    technician: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    planned_hours: float | None = Field(default=None, gt=0)
    status: str | None = None
    description: str | None = None
    source_effort_id: str | None = None
    required_competency: str | None = None
    required_competency_id: str | None = None
    planning_type: str | None = None
    priority: str | None = None
    outside_standard_hours: bool | None = None
    confirmation: str | None = None
    load_profile: LoadProfile | None = None
    allow_locked_overallocation: bool = False

    @field_validator("outside_standard_hours", "load_profile", mode="before")
    @classmethod
    def reject_null_non_nullable_patch_fields(cls, value: object) -> object:
        if value is None:
            raise ValueError(
                "Ce champ ne peut pas être null; omets-le pour ne pas le modifier."
            )
        return value


class SegmentAssignRequest(StrictRequest):
    technician: str


class AllocationMoveRequest(StrictRequest):
    technician: str = Field(min_length=1)
    day: date


class ManualAllocationRequest(StrictRequest):
    technician: str
    day: date
    hours: float = Field(gt=0)
    outside_standard_hours: bool = False
    note: str = ""
    confirmation: str | None = None
    overallocation_policy: OverallocationPolicy | None = None


class QuickShiftRequest(StrictRequest):
    project_number: str
    technician: str
    day: date
    hours: float = Field(gt=0)
    project_name: str = ""
    outside_standard_hours: bool = False
    note: str = ""
    description: str = ""
    confirmation: str = "Confirmée"
