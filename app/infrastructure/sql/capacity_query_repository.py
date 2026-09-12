from __future__ import annotations

from dataclasses import replace
from datetime import date

from ...application.query_models import PlanningSnapshotReadModel
from .medium_term_capacity_query import build_medium_term_capacity_buckets
from .query_repository import SqlPlannerQueryRepository as _BaseSqlPlannerQueryRepository


class SqlPlannerQueryRepository(_BaseSqlPlannerQueryRepository):
    """SQL web read repository enriched with medium-term capacity projections."""

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
