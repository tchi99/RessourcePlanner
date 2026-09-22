from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from ...domain.active_days import normalize_active_day_target, split_total_workforce_hours
from .command_adapters import SqlApprovedDemandSyncAdapter
from .models import ResourceRequirement, WorkforceRequest


class SqlEstimatedDaysApprovedDemandSyncAdapter(SqlApprovedDemandSyncAdapter):
    """Legacy request materialization with explicit hours/days/resource semantics.

    Hours are authoritative total workforce effort. Days only guide the eventual
    distribution. Resource count controls parallelism. Existing materialized hours are
    retained as a compatibility total for an old request that predates an hours value;
    otherwise a days-only request is rejected instead of inventing an 8h day.
    """

    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self._estimated_days_session = session

    def _hours_per_resource(
        self,
        request: WorkforceRequest,
        desired: int,
        current: list[ResourceRequirement],
    ) -> Decimal:
        if request.estimated_hours is not None and request.estimated_hours > 0:
            return (request.estimated_hours / Decimal(desired)).quantize(Decimal("0.01"))

        existing_total = sum(
            (row.planned_hours for row in current if row.planned_hours > 0),
            Decimal("0"),
        )
        if existing_total > 0:
            return (existing_total / Decimal(desired)).quantize(Decimal("0.01"))

        if request.estimated_days is not None and request.estimated_days > 0:
            raise ValueError(
                "Les jours estimés guident la répartition mais ne définissent pas les heures. "
                "Renseigne les heures estimées avant d'approuver cette demande."
            )
        raise ValueError(
            "Les heures estimées sont requises pour matérialiser une nouvelle demande."
        )

    def prevalidate_approved(self, demand_number: str) -> None:
        """Validate legacy effort semantics without mutating materialized planning."""

        request = self._request(demand_number)
        if request.estimated_hours is not None and request.estimated_hours > 0:
            return
        current = self._active_requirements(request)
        existing_total = sum(
            (row.planned_hours for row in current if row.planned_hours > 0),
            Decimal("0"),
        )
        if existing_total > 0:
            return
        self._hours_per_resource(
            request,
            max(int(request.resource_count or 1), 1),
            current,
        )

    def sync_approved(self, demand_number: str) -> None:
        self.prevalidate_approved(demand_number)
        request = self._request(demand_number)
        current_before = self._active_requirements(request)
        if request.estimated_hours is not None and request.estimated_hours > 0:
            total_hours = float(request.estimated_hours)
        else:
            total_hours = float(
                sum(
                    (row.planned_hours for row in current_before if row.planned_hours > 0),
                    Decimal("0"),
                )
            )
            if total_hours <= 0:
                # Delegate to the overridden resolver so the user receives the precise
                # hours-vs-days business error before any mutation is made.
                self._hours_per_resource(
                    request,
                    max(int(request.resource_count or 1), 1),
                    current_before,
                )

        start = request.desired_start
        end = request.desired_end or start
        target_days = normalize_active_day_target(
            request.estimated_days,
            start=start,
            end=end,
            field="Les jours estimés de la demande",
        )

        super().sync_approved(demand_number)
        current = self._active_requirements(request)
        split = split_total_workforce_hours(total_hours, len(current))
        for requirement, hours in zip(current, split):
            requirement.planned_hours = Decimal(str(hours)).quantize(Decimal("0.01"))
            requirement.desired_active_days = target_days
        self._estimated_days_session.flush()
