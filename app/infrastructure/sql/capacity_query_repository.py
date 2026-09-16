from __future__ import annotations

from dataclasses import replace
from datetime import date

from ...application.query_models import PlanningSnapshotReadModel, ShiftReadModel
from .medium_term_capacity_query import build_medium_term_capacity_buckets
from .query_repository import SqlPlannerQueryRepository as _BaseSqlPlannerQueryRepository


class SqlPlannerQueryRepository(_BaseSqlPlannerQueryRepository):
    """SQL web read repository enriched with medium-term capacity projections."""

    def list_shifts(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
        resource_name: str | None = None,
        resource_id: str | None = None,
    ) -> tuple[ShiftReadModel, ...]:
        rows = super().list_shifts(
            start=start,
            end=end,
            resource_name=resource_name,
        )
        wanted_id = str(resource_id or "").strip()
        if not wanted_id:
            return rows
        return tuple(row for row in rows if row.resource_id == wanted_id)

    def planning_snapshot(self, *, start: date, end: date) -> PlanningSnapshotReadModel:
        snapshot = super().planning_snapshot(start=start, end=end)
        return replace(
            snapshot,
            capacity_buckets=build_medium_term_capacity_buckets(
                self,
                self._session,
                start=start,
                end=end,
            ),
        )
