from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Protocol

from .query_models import (
    PendingDemandLoadReadModel,
    PlanningSnapshotReadModel,
    ProjectReadModel,
    ResourceAvailabilityRuleReadModel,
    ResourceReadModel,
    ShiftReadModel,
    WorkPackageReadModel,
)
from .read_models import DemandPeriodReadModel, DemandReadModel, SegmentReadModel


class PlannerQueryPort(Protocol):
    """Read-only canonical query surface required by web clients."""

    def list_projects(self, *, active_only: bool = False) -> Sequence[ProjectReadModel]: ...

    def list_work_packages(
        self,
        *,
        project_number: str | None = None,
        active_only: bool = True,
    ) -> Sequence[WorkPackageReadModel]: ...

    def list_resources(self, *, active_only: bool = True) -> Sequence[ResourceReadModel]: ...

    def list_availability_rules(
        self,
        *,
        resource_id: str | None = None,
        include_global: bool = True,
        active_only: bool = True,
    ) -> Sequence[ResourceAvailabilityRuleReadModel]: ...

    def list_schedulable_resources(
        self,
        *,
        start: date,
        end: date,
    ) -> Sequence[ResourceReadModel]: ...

    def list_demands(self) -> Sequence[DemandReadModel]: ...

    def get_demand(self, number: str) -> DemandReadModel | None: ...

    def list_demand_periods(self, number: str) -> Sequence[DemandPeriodReadModel]: ...

    def list_pending_loads(
        self,
        *,
        start: date,
        end: date,
    ) -> Sequence[PendingDemandLoadReadModel]: ...

    def list_segments(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
        include_cancelled: bool = False,
    ) -> Sequence[SegmentReadModel]: ...

    def get_segment(self, segment_id: str) -> SegmentReadModel | None: ...

    def list_shifts(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
        resource_name: str | None = None,
        resource_id: str | None = None,
    ) -> Sequence[ShiftReadModel]: ...

    def planning_snapshot(
        self,
        *,
        start: date,
        end: date,
    ) -> PlanningSnapshotReadModel: ...
