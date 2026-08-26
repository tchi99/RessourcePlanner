from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Protocol

from .query_models import (
    PlanningSnapshotReadModel,
    ProjectReadModel,
    ResourceReadModel,
    ShiftReadModel,
)
from .read_models import DemandReadModel, SegmentReadModel


class PlannerQueryPort(Protocol):
    """Read-only canonical query surface required by web clients.

    Implementations may use SQL Server, SQLite or another store. The HTTP layer must
    never inspect SQLAlchemy models or legacy Excel column names.
    """

    def list_projects(self, *, active_only: bool = False) -> Sequence[ProjectReadModel]: ...

    def list_resources(self, *, active_only: bool = True) -> Sequence[ResourceReadModel]: ...

    def list_demands(self) -> Sequence[DemandReadModel]: ...

    def get_demand(self, number: str) -> DemandReadModel | None: ...

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
    ) -> Sequence[ShiftReadModel]: ...

    def planning_snapshot(
        self,
        *,
        start: date,
        end: date,
    ) -> PlanningSnapshotReadModel: ...
