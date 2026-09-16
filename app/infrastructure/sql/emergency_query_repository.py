from __future__ import annotations

from dataclasses import replace

from sqlalchemy import select
from sqlalchemy.orm import Session

from .emergency_demand_repository import SqlEmergencyDemandRepository
from .models import WorkforceRequest
from .plan_delta_query_repository import SqlPlannerQueryRepositoryWithPlanDelta


class SqlPlannerQueryRepositoryWithEmergencyOverride(
    SqlPlannerQueryRepositoryWithPlanDelta
):
    """Canonical web reads enriched with emergency-override indicators."""

    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self._emergency_session = session
        self._demands = SqlEmergencyDemandRepository(session)

    def list_shifts(self, **kwargs):
        rows = super().list_shifts(**kwargs)
        demand_numbers = {row.demand_number for row in rows if row.demand_number}
        if not demand_numbers:
            return rows

        requests = self._emergency_session.scalars(
            select(WorkforceRequest).where(
                (
                    WorkforceRequest.legacy_demand_number.in_(demand_numbers)
                    | WorkforceRequest.id.in_(demand_numbers)
                )
            )
        ).all()
        active = {
            (request.legacy_demand_number or request.id): bool(
                request.emergency_override_active
            )
            for request in requests
        }
        return tuple(
            replace(
                row,
                emergency_override_active=bool(
                    row.demand_number and active.get(row.demand_number, False)
                ),
            )
            for row in rows
        )
