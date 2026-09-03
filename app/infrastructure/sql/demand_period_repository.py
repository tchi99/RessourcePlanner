from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...application.read_models import DemandPeriodReadModel
from ...application.repository_ports import DemandPeriodRepositoryPort
from ...domain.confirmation import normalize_confirmation
from ...domain.demand_periods import DemandPeriodDefinition, validate_period_definitions
from .base import utc_now
from .demand_period_models import (
    WorkforceRequestPeriod,
    WorkforceRequestPeriodSelection,
)
from .models import Resource, WorkforceRequest, WorkforceRequestHistory


def _text(value: object) -> str:
    return str(value or "").strip()


class SqlDemandPeriodRepository(DemandPeriodRepositoryPort):
    """SQL storage for request periods without leaking SQLAlchemy into the core."""

    def __init__(self, session: Session, *, actor_name: str = "") -> None:
        self._session = session
        self._actor_name = _text(actor_name)

    def _request(self, number: str) -> WorkforceRequest:
        wanted = _text(number)
        request = self._session.scalar(
            select(WorkforceRequest).where(
                (WorkforceRequest.legacy_demand_number == wanted)
                | (WorkforceRequest.id == wanted)
            )
        )
        if request is None:
            raise KeyError(f"Demande {wanted} introuvable")
        return request

    def _resource(self, name: str | None) -> Resource | None:
        wanted = _text(name)
        if not wanted:
            return None
        resource = self._session.scalar(select(Resource).where(Resource.name == wanted))
        if resource is None:
            raise KeyError(f"Ressource {wanted} introuvable")
        return resource

    def _selection_row_ids(self, request_id: str) -> dict[str, str]:
        rows = self._session.scalars(
            select(WorkforceRequestPeriodSelection).where(
                WorkforceRequestPeriodSelection.workforce_request_id == request_id
            )
        ).all()
        return {row.alternative_group: row.period_id for row in rows}

    def list_for_demand(
        self,
        demand_number: str,
        *,
        include_inactive: bool = False,
    ) -> Sequence[DemandPeriodReadModel]:
        request = self._request(demand_number)
        statement = select(WorkforceRequestPeriod).where(
            WorkforceRequestPeriod.workforce_request_id == request.id
        )
        if not include_inactive:
            statement = statement.where(WorkforceRequestPeriod.active.is_(True))
        periods = self._session.scalars(
            statement.order_by(
                WorkforceRequestPeriod.sequence,
                WorkforceRequestPeriod.created_at,
                WorkforceRequestPeriod.id,
            )
        ).all()
        selections = self._selection_row_ids(request.id)
        resource_ids = {row.proposed_resource_id for row in periods if row.proposed_resource_id}
        resources = (
            self._session.scalars(select(Resource).where(Resource.id.in_(resource_ids))).all()
            if resource_ids
            else []
        )
        resource_names = {row.id: row.name for row in resources}
        business_number = _text(request.legacy_demand_number) or request.id
        return tuple(
            DemandPeriodReadModel(
                period_id=row.period_key,
                demand_number=business_number,
                sequence=row.sequence,
                kind=row.kind,
                alternative_group=row.alternative_group,
                start_date=row.start_date,
                end_date=row.end_date,
                hours=float(row.hours),
                confirmation=row.confirmation,
                proposed_resource=resource_names.get(row.proposed_resource_id),
                resource_count=row.resource_count,
                note=row.note,
                selected=(
                    bool(row.alternative_group)
                    and selections.get(_text(row.alternative_group)) == row.id
                ),
            )
            for row in periods
        )

    def replace_for_demand(
        self,
        demand_number: str,
        periods: Sequence[DemandPeriodDefinition],
    ) -> Sequence[DemandPeriodReadModel]:
        validate_period_definitions(periods)
        request = self._request(demand_number)

        # Previous physical rows are retained for audit/history. Stable period keys
        # may therefore be reused by a newer request version without a PK collision.
        current = self._session.scalars(
            select(WorkforceRequestPeriod).where(
                WorkforceRequestPeriod.workforce_request_id == request.id,
                WorkforceRequestPeriod.active.is_(True),
            )
        ).all()
        for row in current:
            row.active = False

        old_selections = self._session.scalars(
            select(WorkforceRequestPeriodSelection).where(
                WorkforceRequestPeriodSelection.workforce_request_id == request.id
            )
        ).all()
        for selection in old_selections:
            self._session.delete(selection)
        self._session.flush()

        for sequence, period in enumerate(periods, start=1):
            resource = self._resource(period.proposed_resource)
            self._session.add(
                WorkforceRequestPeriod(
                    period_key=_text(period.period_id),
                    workforce_request_id=request.id,
                    sequence=sequence,
                    kind=_text(period.kind).upper(),
                    alternative_group=_text(period.alternative_group) or None,
                    start_date=period.start_date,
                    end_date=period.end_date,
                    hours=Decimal(str(period.hours)),
                    confirmation=normalize_confirmation(period.confirmation),
                    proposed_resource_id=resource.id if resource is not None else None,
                    resource_count=int(period.resource_count),
                    note=_text(period.note) or None,
                    active=True,
                )
            )
        self._session.flush()
        return self.list_for_demand(demand_number)

    def select_alternative(
        self,
        demand_number: str,
        alternative_group: str,
        period_id: str,
    ) -> None:
        request = self._request(demand_number)
        group = _text(alternative_group)
        wanted = _text(period_id)
        period = self._session.scalar(
            select(WorkforceRequestPeriod).where(
                WorkforceRequestPeriod.period_key == wanted,
                WorkforceRequestPeriod.workforce_request_id == request.id,
                WorkforceRequestPeriod.active.is_(True),
            )
        )
        if period is None:
            raise KeyError(f"Période {wanted} introuvable pour la demande")
        if period.kind != "ALTERNATIVE" or _text(period.alternative_group) != group:
            raise ValueError(
                f"La période {wanted} n'appartient pas au groupe alternatif {group}."
            )

        selection = self._session.scalar(
            select(WorkforceRequestPeriodSelection).where(
                WorkforceRequestPeriodSelection.workforce_request_id == request.id,
                WorkforceRequestPeriodSelection.alternative_group == group,
            )
        )
        previous_period = (
            self._session.get(WorkforceRequestPeriod, selection.period_id)
            if selection is not None
            else None
        )
        if selection is not None and selection.period_id == period.id:
            return

        selected_at = utc_now()
        if selection is None:
            selection = WorkforceRequestPeriodSelection(
                workforce_request_id=request.id,
                alternative_group=group,
                period_id=period.id,
                selected_at=selected_at,
                selected_by_name=self._actor_name or None,
            )
            self._session.add(selection)
        else:
            selection.period_id = period.id
            selection.selected_at = selected_at
            selection.selected_by_name = self._actor_name or None

        previous_key = _text(previous_period.period_key) if previous_period is not None else ""
        self._session.add(
            WorkforceRequestHistory(
                workforce_request_id=request.id,
                action="Sélection alternative",
                status=request.status,
                comment=(
                    f"Groupe {group}: {previous_key or 'aucune'} -> {period.period_key}"
                ),
                actor_name=self._actor_name or None,
                occurred_at=selected_at,
            )
        )
        self._session.flush()

    def selections_for_demand(self, demand_number: str) -> Mapping[str, str]:
        request = self._request(demand_number)
        rows = self._session.execute(
            select(WorkforceRequestPeriodSelection, WorkforceRequestPeriod)
            .join(
                WorkforceRequestPeriod,
                WorkforceRequestPeriodSelection.period_id == WorkforceRequestPeriod.id,
            )
            .where(
                WorkforceRequestPeriodSelection.workforce_request_id == request.id
            )
        ).all()
        return {
            selection.alternative_group: period.period_key
            for selection, period in rows
        }
