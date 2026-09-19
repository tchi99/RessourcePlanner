from __future__ import annotations

from dataclasses import replace
from collections.abc import Sequence
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
        project_ids: Sequence[str] | None = None,
    ) -> tuple[ShiftReadModel, ...]:
        return super().list_shifts(
            start=start,
            end=end,
            resource_name=resource_name,
            resource_id=resource_id,
            project_ids=project_ids,
        )

    def planning_snapshot(
        self,
        *,
        start: date,
        end: date,
        project_ids: Sequence[str] | None = None,
        include_resource_ids: Sequence[str] = (),
    ) -> PlanningSnapshotReadModel:
        snapshot = super().planning_snapshot(
            start=start,
            end=end,
            project_ids=project_ids,
            include_resource_ids=include_resource_ids,
        )
        # Medium-term capacity remains an organization-wide reference. The contextual
        # scope filters projects/work packages/cards, not the company's capacity pool.
        return replace(
            snapshot,
            capacity_buckets=build_medium_term_capacity_buckets(
                self,
                self._session,
                start=start,
                end=end,
            ),
        )
