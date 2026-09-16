from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...application.command_ports import ApprovedDemandSyncPort
from ...domain.confirmation import CONFIRMATION_CONFIRMED, normalize_confirmation
from ...domain.demand_periods import PERIOD_KIND_CUMULATIVE
from .base import utc_now
from .command_adapters import SqlApprovedDemandSyncAdapter
from .demand_period_models import (
    WorkforceRequestPeriod,
    WorkforceRequestPeriodRequirement,
    WorkforceRequestPeriodSelection,
)
from .models import (
    ORIGIN_REQUEST,
    Project,
    Resource,
    ResourceRequirement,
    WorkforceRequest,
    WorkforceRequestHistory,
)
from .segment_repository import SqlSegmentRepository


def _text(value: object) -> str:
    return str(value or "").strip()


class SqlPeriodAwareApprovedDemandSyncAdapter(ApprovedDemandSyncPort):
    """Materialize an approved or explicitly emergency request period definition."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._segments = SqlSegmentRepository(session)
        self._legacy = SqlApprovedDemandSyncAdapter(session)

    def _request(self, number: str) -> WorkforceRequest:
        wanted = _text(number)
        request = self._session.scalar(
            select(WorkforceRequest).where(
                (WorkforceRequest.legacy_demand_number == wanted)
                | (WorkforceRequest.id == wanted)
            )
        )
        if request is None:
            raise KeyError(f"Demande {wanted} introuvable après approbation")
        return request

    @staticmethod
    def _emergency_materialization(request: WorkforceRequest) -> bool:
        return bool(request.emergency_override_active) and request.status == "Soumise"

    def _active_periods(self, request_id: str) -> list[WorkforceRequestPeriod]:
        return list(
            self._session.scalars(
                select(WorkforceRequestPeriod)
                .where(
                    WorkforceRequestPeriod.workforce_request_id == request_id,
                    WorkforceRequestPeriod.active.is_(True),
                )
                .order_by(
                    WorkforceRequestPeriod.sequence,
                    WorkforceRequestPeriod.created_at,
                    WorkforceRequestPeriod.id,
                )
            ).all()
        )

    def _selected_period_ids(self, request_id: str) -> dict[str, str]:
        rows = self._session.scalars(
            select(WorkforceRequestPeriodSelection).where(
                WorkforceRequestPeriodSelection.workforce_request_id == request_id
            )
        ).all()
        return {row.alternative_group: row.period_id for row in rows}

    def _active_requirements(self, request_id: str) -> list[ResourceRequirement]:
        return list(
            self._session.scalars(
                select(ResourceRequirement)
                .where(
                    ResourceRequirement.workforce_request_id == request_id,
                    ResourceRequirement.status != "Annulé",
                )
                .order_by(ResourceRequirement.created_at, ResourceRequirement.id)
            ).all()
        )

    def _requirement_links(self, requirement_ids: set[str]) -> dict[str, str]:
        if not requirement_ids:
            return {}
        rows = self._session.scalars(
            select(WorkforceRequestPeriodRequirement).where(
                WorkforceRequestPeriodRequirement.resource_requirement_id.in_(requirement_ids)
            )
        ).all()
        return {row.resource_requirement_id: row.period_id for row in rows}

    def _create_requirement(
        self,
        *,
        request: WorkforceRequest,
        project: Project,
        period: WorkforceRequestPeriod,
        proposed: Resource | None,
    ) -> ResourceRequirement:
        identifier = self._segments.create(
            {
                "NoDemande": _text(request.legacy_demand_number) or request.id,
                "NumeroProjet": project.number,
                "Technicien": proposed.name if proposed is not None else None,
                "DateDebut": period.start_date,
                "DateFin": period.end_date,
                "HeuresPrevues": period.hours,
                "Statut": "Planifié" if proposed is not None else "À assigner",
                "Description": period.note or request.description or "Période approuvée",
                "CompetenceRequise": request.required_competencies,
                "TypePlanification": "Flexible",
                "Priorite": request.priority or "Normale",
                "HorsHoraireAutorise": False,
                "OrigineSegment": ORIGIN_REQUEST,
                "Confirmation": normalize_confirmation(
                    period.confirmation,
                    default=CONFIRMATION_CONFIRMED,
                ),
                "ConfirmationOverride": False,
            }
        )
        requirement = self._session.scalar(
            select(ResourceRequirement).where(
                ResourceRequirement.legacy_segment_id == identifier
            )
        )
        if requirement is None:
            raise RuntimeError("Le besoin créé pour la période approuvée est introuvable.")
        self._session.add(
            WorkforceRequestPeriodRequirement(
                resource_requirement_id=requirement.id,
                period_id=period.id,
            )
        )
        self._session.flush()
        return requirement

    def sync_approved(self, demand_number: str) -> None:
        request = self._request(demand_number)
        periods = self._active_periods(request.id)
        if not periods:
            self._legacy.sync_approved(demand_number)
            return

        project = self._session.get(Project, request.project_id)
        if project is None:
            raise KeyError(f"Projet {request.project_id} introuvable")

        selected = self._selected_period_ids(request.id)
        effective = [
            period
            for period in periods
            if period.kind == PERIOD_KIND_CUMULATIVE
            or (
                period.alternative_group is not None
                and selected.get(period.alternative_group) == period.id
            )
        ]
        effective_ids = {period.id for period in effective}

        current = self._active_requirements(request.id)
        links = self._requirement_links({row.id for row in current})
        by_period: dict[str, list[ResourceRequirement]] = defaultdict(list)
        for requirement in current:
            period_id = links.get(requirement.id)
            if period_id not in effective_ids:
                requirement.status = "Annulé"
                continue
            by_period[period_id].append(requirement)

        for period in effective:
            desired = max(int(period.resource_count or 1), 1)
            rows = by_period.get(period.id, [])
            proposed = (
                self._session.get(Resource, period.proposed_resource_id)
                if period.proposed_resource_id
                else None
            )
            if period.proposed_resource_id and proposed is None:
                raise KeyError(
                    f"Ressource proposée introuvable pour la période {period.period_key}."
                )

            while len(rows) < desired:
                rows.append(
                    self._create_requirement(
                        request=request,
                        project=project,
                        period=period,
                        proposed=proposed,
                    )
                )

            if len(rows) > desired:
                ranked = sorted(
                    rows,
                    key=lambda row: (
                        0 if row.assigned_resource_id else 1,
                        row.created_at,
                        row.id,
                    ),
                )
                keep_ids = {row.id for row in ranked[:desired]}
                for requirement in rows:
                    if requirement.id not in keep_ids:
                        requirement.status = "Annulé"
                rows = [row for row in ranked if row.id in keep_ids]

            inherited_confirmation = normalize_confirmation(
                period.confirmation,
                default=CONFIRMATION_CONFIRMED,
            )
            for requirement in rows:
                if proposed is not None and not requirement.assigned_resource_id:
                    requirement.assigned_resource_id = proposed.id
                if requirement.assigned_resource_id:
                    requirement.status = "Planifié"
                elif requirement.status not in {"Terminé", "Annulé"}:
                    requirement.status = "À assigner"

                requirement.project_id = request.project_id
                requirement.start_date = period.start_date
                requirement.end_date = period.end_date
                requirement.planned_hours = period.hours
                requirement.description = period.note or request.description or ""
                requirement.required_competency = request.required_competencies
                requirement.priority = request.priority or "Normale"
                requirement.origin = ORIGIN_REQUEST
                if not requirement.confirmation_overridden:
                    requirement.confirmation = inherited_confirmation

        groups = sorted(
            {
                _text(period.alternative_group)
                for period in periods
                if period.alternative_group
            }
        )
        unresolved = [group for group in groups if group not in selected]
        emergency = self._emergency_materialization(request)
        self._session.add(
            WorkforceRequestHistory(
                workforce_request_id=request.id,
                action=(
                    "Synchronisation périodes urgente"
                    if emergency
                    else "Synchronisation périodes"
                ),
                status=request.status,
                comment=(
                    f"{len(effective)} période(s) effective(s) matérialisée(s) par dérogation urgente; "
                    f"{len(unresolved)} groupe(s) alternatif(s) non résolu(s)."
                    if emergency
                    else (
                        f"{len(effective)} période(s) effective(s), "
                        f"{len(unresolved)} groupe(s) alternatif(s) non résolu(s)."
                    )
                ),
                actor_name=(
                    request.emergency_override_by_name
                    if emergency
                    else request.approved_by_name
                ),
                occurred_at=utc_now(),
            )
        )
        self._session.flush()