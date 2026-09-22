from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
import json
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...application.plan_delta import (
    DemandApprovalStateReadModel,
    DemandPlanDeltaDiagnosticReadModel,
    DemandPlanDeltaItemReadModel,
    DemandPlanDeltaReadModel,
)
from ...domain.active_days import split_total_workforce_hours
from ...domain.availability_rules import availability_hours_for_day
from ...domain.confirmation import CONFIRMATION_CONFIRMED, normalize_confirmation
from ...domain.plan_comparison import (
    AllocationDifference,
    AllocationProjection,
    compare_allocation_plans,
)
from ...domain.planning_engine import build_allocation_plan
from ...domain.planning_projection import project_planning_snapshot
from ...domain.planning_snapshot import PlanningSnapshot
from .approval_revision_models import (
    APPROVAL_REFERENCE_CAPTURED,
    RequestApprovalReference,
    RequestApprovalRevision,
)
from .approval_revision_repository import SqlRequestApprovalRevisionRepository
from .approval_envelope_policy_repository import (
    SqlDemandApprovalEnvelopePolicyRepository,
)
from .demand_period_models import (
    WorkforceRequestPeriod,
    WorkforceRequestPeriodRequirement,
    WorkforceRequestPeriodSelection,
)
from .models import (
    ORIGIN_REQUEST,
    Project,
    RequestLine,
    Resource,
    ResourceRequirement,
    WorkforceRequest,
    WorkPackage,
)
from .operational_choice_models import RequestOperationalState
from .planning_repository import SqlPlanningReadRepository
from .request_plan_preparation import SqlRequestPlanPreparer
from .web_query_repository import SqlPlannerQueryRepositoryWeb


INACTIVE_REQUIREMENT_STATUSES = {"Annulé", "Terminé"}


def _text(value: object) -> str:
    return str(value or "").strip()


def _identifier(requirement: ResourceRequirement) -> str:
    return _text(requirement.legacy_segment_id) or requirement.id


def _allocation_projection(result: object) -> tuple[AllocationProjection, ...]:
    allocations = getattr(result, "allocations", ())
    return tuple(
        AllocationProjection(
            segment_id=row.segment_id,
            resource_id=row.resource_id,
            day=row.day,
            hours=float(row.hours),
            allocation_type=row.allocation_type,
            locked=bool(row.locked),
            outside_schedule=bool(row.outside_schedule),
        )
        for row in allocations
        if bool(getattr(row, "counts_as_allocated", True))
    )


def _item_from_difference(
    difference: AllocationDifference,
    *,
    change: str,
    resource_id_by_name: dict[str, str] | None = None,
) -> DemandPlanDeltaItemReadModel:
    current = difference.legacy_hours > 0
    proposed = difference.shadow_hours > 0
    return DemandPlanDeltaItemReadModel(
        change=change,
        segment_id=difference.segment_id,
        current_resource_name=difference.resource_id if current else None,
        proposed_resource_name=difference.resource_id if proposed else None,
        current_resource_id=(
            (resource_id_by_name or {}).get(difference.resource_id) if current else None
        ),
        proposed_resource_id=(
            (resource_id_by_name or {}).get(difference.resource_id) if proposed else None
        ),
        current_date=difference.day if current else None,
        proposed_date=difference.day if proposed else None,
        current_hours=float(difference.legacy_hours),
        proposed_hours=float(difference.shadow_hours),
        current_allocation_type=difference.allocation_type if current else None,
        proposed_allocation_type=difference.allocation_type if proposed else None,
        current_outside_standard_hours=(
            bool(difference.outside_schedule) if current else False
        ),
        proposed_outside_standard_hours=(
            bool(difference.outside_schedule) if proposed else False
        ),
        locked=bool(difference.locked),
    )


def _delta_items(
    differences: tuple[AllocationDifference, ...],
    *,
    resource_id_by_name: dict[str, str] | None = None,
) -> tuple[DemandPlanDeltaItemReadModel, ...]:
    """Turn semantic-key differences into coordinator-friendly add/move/change/cancel rows."""

    direct: list[DemandPlanDeltaItemReadModel] = []
    old_only: dict[str, list[AllocationDifference]] = defaultdict(list)
    new_only: dict[str, list[AllocationDifference]] = defaultdict(list)

    for difference in differences:
        if difference.legacy_hours > 0 and difference.shadow_hours > 0:
            direct.append(_item_from_difference(
                difference,
                change="MODIFY",
                resource_id_by_name=resource_id_by_name,
            ))
        elif difference.legacy_hours > 0:
            old_only[difference.segment_id].append(difference)
        elif difference.shadow_hours > 0:
            new_only[difference.segment_id].append(difference)

    for segment_id in sorted(set(old_only) | set(new_only)):
        old_rows = sorted(old_only.get(segment_id, []), key=lambda row: (row.day, row.resource_id))
        new_rows = sorted(new_only.get(segment_id, []), key=lambda row: (row.day, row.resource_id))
        used_new: set[int] = set()

        for old in old_rows:
            pair_index = next(
                (
                    index
                    for index, candidate in enumerate(new_rows)
                    if index not in used_new
                    and abs(float(candidate.shadow_hours) - float(old.legacy_hours)) <= 0.01
                ),
                None,
            )
            if pair_index is None:
                direct.append(_item_from_difference(
                    old,
                    change="CANCEL",
                    resource_id_by_name=resource_id_by_name,
                ))
                continue
            new = new_rows[pair_index]
            used_new.add(pair_index)
            direct.append(
                DemandPlanDeltaItemReadModel(
                    change="MOVE",
                    segment_id=segment_id,
                    current_resource_name=old.resource_id,
                    proposed_resource_name=new.resource_id,
                    current_resource_id=(resource_id_by_name or {}).get(old.resource_id),
                    proposed_resource_id=(resource_id_by_name or {}).get(new.resource_id),
                    current_date=old.day,
                    proposed_date=new.day,
                    current_hours=float(old.legacy_hours),
                    proposed_hours=float(new.shadow_hours),
                    current_allocation_type=old.allocation_type,
                    proposed_allocation_type=new.allocation_type,
                    current_outside_standard_hours=bool(old.outside_schedule),
                    proposed_outside_standard_hours=bool(new.outside_schedule),
                    locked=bool(old.locked or new.locked),
                )
            )

        for index, new in enumerate(new_rows):
            if index not in used_new:
                direct.append(_item_from_difference(
                    new,
                    change="ADD",
                    resource_id_by_name=resource_id_by_name,
                ))

    order = {"CANCEL": 0, "MOVE": 1, "MODIFY": 2, "ADD": 3}
    return tuple(
        sorted(
            direct,
            key=lambda row: (
                order.get(row.change, 9),
                row.current_date or row.proposed_date,
                row.segment_id,
            ),
        )
    )


class SqlPlannerQueryRepositoryWithPlanDelta(SqlPlannerQueryRepositoryWeb):
    """React query surface with a non-mutating preview of a pending reapproval."""

    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self._delta_session = session
        self._plan_preparer = SqlRequestPlanPreparer(session)

    def _request(self, number: str) -> WorkforceRequest | None:
        wanted = _text(number)
        if not wanted:
            return None
        return self._delta_session.scalar(
            select(WorkforceRequest).where(
                (WorkforceRequest.legacy_demand_number == wanted)
                | (WorkforceRequest.id == wanted)
            )
        )

    def _current_requirements(self, request_id: str) -> list[ResourceRequirement]:
        return list(
            self._delta_session.scalars(
                select(ResourceRequirement)
                .where(
                    ResourceRequirement.workforce_request_id == request_id,
                    ResourceRequirement.status != "Annulé",
                )
                .order_by(ResourceRequirement.created_at, ResourceRequirement.id)
            ).all()
        )

    def _period_key_by_requirement(self, request_id: str) -> dict[str, str]:
        rows = self._delta_session.execute(
            select(WorkforceRequestPeriodRequirement, WorkforceRequestPeriod)
            .join(
                WorkforceRequestPeriod,
                WorkforceRequestPeriodRequirement.period_id == WorkforceRequestPeriod.id,
            )
            .where(WorkforceRequestPeriod.workforce_request_id == request_id)
        ).all()
        return {
            link.resource_requirement_id: period.period_key
            for link, period in rows
        }

    def _period_identity_by_requirement(
        self,
        request_id: str,
    ) -> dict[str, tuple[str, str]]:
        rows = self._delta_session.execute(
            select(WorkforceRequestPeriodRequirement, WorkforceRequestPeriod)
            .join(
                WorkforceRequestPeriod,
                WorkforceRequestPeriodRequirement.period_id == WorkforceRequestPeriod.id,
            )
            .where(WorkforceRequestPeriod.workforce_request_id == request_id)
        ).all()
        return {
            link.resource_requirement_id: (
                _text(period.request_line_id),
                period.period_key,
            )
            for link, period in rows
            if _text(period.request_line_id)
        }

    def _selected_period_ids_by_line(
        self,
        request_id: str,
    ) -> dict[tuple[str, str], str]:
        rows = self._delta_session.scalars(
            select(WorkforceRequestPeriodSelection).where(
                WorkforceRequestPeriodSelection.workforce_request_id == request_id
            )
        ).all()
        return {
            (row.request_line_id, row.alternative_group): row.period_id
            for row in rows
        }

    def _active_periods(self, request_id: str) -> list[WorkforceRequestPeriod]:
        return list(
            self._delta_session.scalars(
                select(WorkforceRequestPeriod)
                .where(
                    WorkforceRequestPeriod.workforce_request_id == request_id,
                    WorkforceRequestPeriod.active.is_(True),
                )
                .order_by(WorkforceRequestPeriod.sequence, WorkforceRequestPeriod.id)
            ).all()
        )

    def _effective_periods(
        self,
        request_id: str,
        *,
        active_periods: list[WorkforceRequestPeriod] | None = None,
    ) -> list[WorkforceRequestPeriod]:
        periods = active_periods if active_periods is not None else self._active_periods(request_id)
        selections = {
            row.alternative_group: row.period_id
            for row in self._delta_session.scalars(
                select(WorkforceRequestPeriodSelection).where(
                    WorkforceRequestPeriodSelection.workforce_request_id == request_id
                )
            ).all()
        }
        return [
            period
            for period in periods
            if period.kind == "CUMULATIVE"
            or selections.get(_text(period.alternative_group)) == period.id
        ]

    def _legacy_hours_per_resource(
        self,
        request: WorkforceRequest,
        desired: int,
        current: list[ResourceRequirement],
        proposed_resource: Resource | None,
        snapshot: PlanningSnapshot,
    ) -> float | None:
        if request.estimated_hours is not None and request.estimated_hours > 0:
            return float(
                (request.estimated_hours / Decimal(desired)).quantize(Decimal("0.01"))
            )
        if (
            request.estimated_days is not None
            and request.estimated_days > 0
            and proposed_resource is not None
            and request.desired_start is not None
        ):
            end = request.desired_end or request.desired_start
            capacities: list[float] = []
            cursor = request.desired_start
            while cursor <= end:
                capacity = availability_hours_for_day(
                    snapshot.availability,
                    proposed_resource.name,
                    cursor,
                )
                if capacity > 0:
                    capacities.append(capacity)
                cursor += timedelta(days=1)
            if capacities:
                return round(float(request.estimated_days) * (sum(capacities) / len(capacities)), 2)
        existing = [float(row.planned_hours) for row in current if row.planned_hours > 0]
        return round(sum(existing) / len(existing), 2) if existing else None

    def _segment_row(
        self,
        *,
        requirement: ResourceRequirement | None,
        request: WorkforceRequest,
        project: Project,
        resource: Resource | None,
        start_date: object,
        end_date: object,
        hours: float,
        confirmation: str,
        description: str | None,
        synthetic_id: str,
    ) -> dict[str, object]:
        assigned = resource is not None
        status = requirement.status if requirement is not None else ("Planifié" if assigned else "À assigner")
        if requirement is not None and assigned and status == "À assigner":
            status = "Planifié"
        if requirement is not None and not assigned and status not in INACTIVE_REQUIREMENT_STATUSES:
            status = "À assigner"
        return {
            "IDSegment": _identifier(requirement) if requirement is not None else synthetic_id,
            "NoDemande": _text(request.legacy_demand_number) or request.id,
            "NumeroProjet": project.number,
            "NomProjet": project.name,
            "Technicien": resource.name if resource is not None else None,
            "DateDebut": start_date,
            "DateFin": end_date,
            "HeuresPrevues": hours,
            "Statut": status,
            "Description": description,
            "SourceEffortID": requirement.source_effort_id if requirement is not None else None,
            "DateCreation": requirement.created_at if requirement is not None else f"preview:{synthetic_id}",
            "CompetenceRequise": (
                requirement.required_competency
                if requirement is not None
                else request.required_competencies
            ),
            "ClasseRessourceRequise": (
                requirement.required_resource_class
                if requirement is not None
                else None
            ),
            "TypePlanification": requirement.planning_type if requirement is not None else "Flexible",
            "Priorite": requirement.priority if requirement is not None else request.priority,
            "HorsHoraireAutorise": (
                requirement.outside_standard_hours_allowed if requirement is not None else False
            ),
            "OrigineSegment": "REQUEST",
            "Confirmation": (
                requirement.confirmation
                if requirement is not None and requirement.confirmation_overridden
                else confirmation
            ),
        }

    def _proposed_line_segments(
        self,
        request: WorkforceRequest,
        current: list[ResourceRequirement],
    ) -> list[dict[str, object]] | None:
        project = self._delta_session.get(Project, request.project_id)
        if project is None:
            return None

        lines = list(
            self._delta_session.scalars(
                select(RequestLine)
                .where(
                    RequestLine.workforce_request_id == request.id,
                    RequestLine.active.is_(True),
                )
                .order_by(RequestLine.position, RequestLine.id)
            ).all()
        )
        if not lines:
            return None

        resources = {
            row.id: row
            for row in self._delta_session.scalars(select(Resource)).all()
        }
        active_periods = self._active_periods(request.id)
        periods_by_line: dict[str, list[WorkforceRequestPeriod]] = defaultdict(list)
        for period in active_periods:
            if period.request_line_id:
                periods_by_line[period.request_line_id].append(period)
        selections = self._selected_period_ids_by_line(request.id)

        period_identity = self._period_identity_by_requirement(request.id)
        current_by_key: dict[tuple[str, ...], list[ResourceRequirement]] = defaultdict(list)
        for requirement in current:
            line_id = _text(requirement.source_request_line_id)
            if not line_id:
                continue
            identity = period_identity.get(requirement.id)
            key = (
                ("PERIOD", identity[0], identity[1])
                if identity is not None
                else ("LINE", line_id)
            )
            current_by_key[key].append(requirement)
        for rows in current_by_key.values():
            rows.sort(
                key=lambda row: (
                    0 if row.assigned_resource_id else 1,
                    row.created_at,
                    row.id,
                )
            )

        package_ids = {line.work_package_id for line in lines if line.work_package_id}
        packages = (
            self._delta_session.scalars(
                select(WorkPackage).where(WorkPackage.id.in_(package_ids))
            ).all()
            if package_ids
            else []
        )
        package_refs = {
            package.id: _text(package.legacy_effort_id) or package.id
            for package in packages
        }

        proposed: list[dict[str, object]] = []
        for line in lines:
            if _text(line.kind) != "WORKFORCE":
                return None
            source_effort_id = (
                package_refs.get(line.work_package_id)
                if line.work_package_id
                else None
            )
            required_competency = _text(line.required_competencies_snapshot) or None
            line_periods = periods_by_line.get(line.id, [])
            if line_periods:
                effective = [
                    period
                    for period in line_periods
                    if period.kind == "CUMULATIVE"
                    or (
                        period.alternative_group is not None
                        and selections.get(
                            (line.id, _text(period.alternative_group))
                        )
                        == period.id
                    )
                ]
                for period in effective:
                    key = ("PERIOD", line.id, period.period_key)
                    requirement = (
                        current_by_key.get(key, [None])[0]
                        if current_by_key.get(key)
                        else None
                    )
                    resource_id = (
                        requirement.assigned_resource_id
                        if requirement is not None and requirement.assigned_resource_id
                        else period.proposed_resource_id or line.proposed_resource_id
                    )
                    row = self._segment_row(
                        requirement=requirement,
                        request=request,
                        project=project,
                        resource=resources.get(resource_id),
                        start_date=period.start_date,
                        end_date=period.end_date,
                        hours=float(period.hours),
                        confirmation=normalize_confirmation(
                            period.confirmation,
                            default=CONFIRMATION_CONFIRMED,
                        ),
                        description=(
                            period.note
                            or line.description
                            or request.description
                            or "Période proposée"
                        ),
                        synthetic_id=f"PREVIEW-{line.id}-{period.period_key}",
                    )
                    proposed.append(
                        {
                            **row,
                            "SourceEffortID": source_effort_id,
                            "ClasseRessourceRequise": line.required_resource_class,
                            "CompetenceRequise": required_competency,
                            "JoursActifsCibles": period.desired_active_days,
                        }
                    )
                continue

            if line.desired_start is None or line.estimated_hours is None:
                return None
            if line.estimated_hours <= 0:
                return None
            key = ("LINE", line.id)
            requirement = (
                current_by_key.get(key, [None])[0]
                if current_by_key.get(key)
                else None
            )
            resource_id = (
                requirement.assigned_resource_id
                if requirement is not None and requirement.assigned_resource_id
                else line.proposed_resource_id
            )
            row = self._segment_row(
                requirement=requirement,
                request=request,
                project=project,
                resource=resources.get(resource_id),
                start_date=line.desired_start,
                end_date=line.desired_end or line.desired_start,
                hours=float(line.estimated_hours),
                confirmation=normalize_confirmation(
                    line.confirmation,
                    default=CONFIRMATION_CONFIRMED,
                ),
                description=(
                    line.description
                    or request.description
                    or "Besoin proposé"
                ),
                synthetic_id=f"PREVIEW-{line.id}",
            )
            proposed.append(
                {
                    **row,
                    "SourceEffortID": source_effort_id,
                    "ClasseRessourceRequise": line.required_resource_class,
                    "CompetenceRequise": required_competency,
                    "JoursActifsCibles": (
                        int(line.desired_active_days)
                        if line.desired_active_days is not None
                        else None
                    ),
                }
            )
        return proposed

    def _proposed_segments(
        self,
        request: WorkforceRequest,
        current: list[ResourceRequirement],
        snapshot: PlanningSnapshot,
    ) -> list[dict[str, object]] | None:
        del snapshot  # preparation is intentionally independent from engine capacity.
        project = self._delta_session.get(Project, request.project_id)
        if project is None:
            return None

        try:
            prepared = self._plan_preparer.prepare(
                request,
                current=current,
            )
        except ValueError:
            return None

        resources = {
            row.id: row
            for row in self._delta_session.scalars(select(Resource)).all()
        }
        matches, _obsolete = self._plan_preparer.match_current(
            request,
            current,
            prepared.specs,
        )

        proposed: list[dict[str, object]] = []
        for match in matches:
            spec = match.spec
            requirement = match.requirement
            resource_id = (
                requirement.assigned_resource_id
                if requirement is not None
                and requirement.assigned_resource_id
                else spec.proposed_resource_id
            )
            row = self._segment_row(
                requirement=requirement,
                request=request,
                project=project,
                resource=resources.get(resource_id),
                start_date=spec.start_date,
                end_date=spec.end_date,
                hours=float(spec.planned_hours),
                confirmation=spec.confirmation,
                description=spec.description,
                synthetic_id=(
                    "PREVIEW-" + "-".join(str(part) for part in spec.key)
                ),
            )
            proposed.append(
                {
                    **row,
                    "SourceEffortID": spec.source_effort_id,
                    "ClasseRessourceRequise": spec.required_resource_class,
                    "CompetenceRequise": spec.required_competency,
                    "JoursActifsCibles": spec.desired_active_days,
                }
            )
        return proposed

    @staticmethod
    def _decoded_mapping(value: str) -> dict[str, str]:
        decoded = json.loads(value or "{}")
        if not isinstance(decoded, dict):
            raise ValueError("L'état opérationnel sérialisé est invalide.")
        return {
            _text(key): _text(item)
            for key, item in decoded.items()
            if _text(key) and _text(item)
        }

    def demand_approval_state(
        self,
        number: str,
    ) -> DemandApprovalStateReadModel | None:
        request = self._request(number)
        if request is None:
            return None

        demand_number = _text(request.legacy_demand_number) or request.id
        diagnostics: list[str] = []
        revisions = SqlRequestApprovalRevisionRepository(self._delta_session)

        candidate_fingerprint: str | None = None
        decision_name: str | None = None
        decision_reason: str | None = None
        decision_changes: tuple[dict[str, object], ...] = ()
        try:
            candidate = revisions.candidate_envelope(request)
            candidate_fingerprint = candidate.authorization_fingerprint
            decision = SqlDemandApprovalEnvelopePolicyRepository(
                self._delta_session
            ).evaluate_candidate(demand_number)
            decision_name = decision.decision
            decision_reason = decision.reason
            decision_changes = tuple(
                dict(row) for row in decision.to_dict()["changes"]
            )
        except ValueError as exc:
            decision_name = "INVALID"
            decision_reason = "INVALID"
            decision_changes = ({"code": "INVALID", "detail": str(exc)},)
            diagnostics.append(f"CANDIDATE_INVALID: {exc}")

        reference = self._delta_session.get(RequestApprovalReference, request.id)
        reference_status = reference.status if reference is not None else None
        revision = (
            self._delta_session.get(
                RequestApprovalRevision,
                reference.active_revision_id,
            )
            if reference is not None and reference.active_revision_id
            else None
        )
        if (
            reference is not None
            and reference.active_revision_id
            and revision is None
        ):
            diagnostics.append("ACTIVE_APPROVAL_REVISION_MISSING")

        selections: dict[str, str] = {}
        confirmations: dict[str, str] = {}
        budget_overrides: dict[str, float] = {}
        operational_version: int | None = None
        if revision is not None:
            state = self._delta_session.get(RequestOperationalState, request.id)
            if state is None:
                diagnostics.append("OPERATIONAL_STATE_MISSING")
            elif state.approval_revision_id != revision.id:
                diagnostics.append("OPERATIONAL_STATE_REVISION_MISMATCH")
            else:
                operational_version = max(int(state.version or 1), 1)
                try:
                    selections = self._decoded_mapping(state.selections_text)
                    confirmations = self._decoded_mapping(
                        state.confirmations_text
                    )
                    budget_overrides = {
                        key: float(value)
                        for key, value in self._decoded_mapping(
                            state.budget_overrides_text
                        ).items()
                    }
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    diagnostics.append(f"OPERATIONAL_STATE_INVALID: {exc}")

        current = [
            row
            for row in self._current_requirements(request.id)
            if row.origin == ORIGIN_REQUEST
        ]
        active_keys = tuple(
            sorted(
                {
                    _text(row.approved_entry_key)
                    for row in current
                    if _text(row.approved_entry_key)
                }
            )
        )
        active_matches: bool | None = None
        if revision is not None:
            active_matches = bool(current) and all(
                row.approval_revision_id == revision.id
                and row.approval_reference_status == APPROVAL_REFERENCE_CAPTURED
                and bool(_text(row.approved_entry_key))
                for row in current
            )

        approved_fingerprint = (
            revision.authorization_fingerprint
            if revision is not None
            else None
        )
        return DemandApprovalStateReadModel(
            demand_number=demand_number,
            candidate_request_version=max(
                int(request.aggregate_version or 1),
                1,
            ),
            approval_reference_status=reference_status,
            active_revision_id=revision.id if revision is not None else None,
            previous_revision_id=(
                revision.previous_revision_id
                if revision is not None
                else None
            ),
            approved_request_version=(
                revision.request_version
                if revision is not None
                else None
            ),
            approved_at=revision.approved_at if revision is not None else None,
            approved_by_name=(
                revision.approved_by_name
                if revision is not None
                else None
            ),
            authorization_fingerprint=approved_fingerprint,
            candidate_authorization_fingerprint=candidate_fingerprint,
            candidate_matches_approved=(
                candidate_fingerprint == approved_fingerprint
                if candidate_fingerprint is not None
                and approved_fingerprint is not None
                else None
            ),
            payload_format_version=(
                revision.payload_format_version
                if revision is not None
                else None
            ),
            operational_version=operational_version,
            envelope_decision=decision_name,
            envelope_reason=decision_reason,
            envelope_changes=decision_changes,
            active_selections=selections,
            active_confirmations=confirmations,
            active_budget_overrides=budget_overrides,
            active_requirement_count=len(current),
            active_planned_hours=round(
                sum(float(row.planned_hours) for row in current),
                2,
            ),
            active_approved_entry_keys=active_keys,
            active_matches_approved_revision=active_matches,
            diagnostics=tuple(diagnostics),
        )

    def demand_plan_delta(self, number: str) -> DemandPlanDeltaReadModel | None:
        request = self._request(number)
        if request is None:
            return None
        demand_number = _text(request.legacy_demand_number) or request.id
        approval_state = self.demand_approval_state(demand_number)

        def delta(**values: object) -> DemandPlanDeltaReadModel:
            values.setdefault("demand_number", demand_number)
            if approval_state is not None:
                values.setdefault(
                    "approval_reference_status",
                    approval_state.approval_reference_status,
                )
                values.setdefault(
                    "active_revision_id",
                    approval_state.active_revision_id,
                )
                values.setdefault(
                    "approved_request_version",
                    approval_state.approved_request_version,
                )
                values.setdefault(
                    "authorization_fingerprint",
                    approval_state.authorization_fingerprint,
                )
                values.setdefault(
                    "candidate_authorization_fingerprint",
                    approval_state.candidate_authorization_fingerprint,
                )
                values.setdefault(
                    "operational_version",
                    approval_state.operational_version,
                )
                values.setdefault(
                    "envelope_decision",
                    approval_state.envelope_decision,
                )
                values.setdefault(
                    "envelope_reason",
                    approval_state.envelope_reason,
                )
            return DemandPlanDeltaReadModel(**values)

        current_requirements = self._current_requirements(request.id)
        if request.status != "Soumise":
            return delta(
                demand_number=demand_number,
                available=False,
                reason="NOT_SUBMITTED",
                has_changes=False,
            )
        if not current_requirements:
            return delta(
                demand_number=demand_number,
                available=False,
                reason="NO_CURRENT_PLAN",
                has_changes=False,
            )

        snapshot = SqlPlanningReadRepository(self._delta_session).capture()
        current_calculation = project_planning_snapshot(snapshot)
        if current_calculation.unsupported_segment_ids:
            return delta(
                demand_number=demand_number,
                available=False,
                reason="CURRENT_PLAN_UNSUPPORTED",
                has_changes=False,
            )

        try:
            prepared = self._plan_preparer.prepare(
                request,
                current=current_requirements,
            )
        except ValueError:
            prepared = None
        if prepared is not None:
            locked_conflicts = self._plan_preparer.locked_conflicts(
                request,
                current_requirements,
                prepared.specs,
            )
            if locked_conflicts:
                return delta(
                    demand_number=demand_number,
                    available=False,
                    reason=locked_conflicts[0].code,
                    has_changes=False,
                    diagnostics=tuple(
                        DemandPlanDeltaDiagnosticReadModel(
                            code=conflict.code,
                            message=conflict.message,
                            requirement_id=conflict.requirement_id,
                            spec_key=conflict.spec_key,
                            shift_ids=conflict.shift_ids,
                        )
                        for conflict in locked_conflicts
                    ),
                )

        proposed_rows = self._proposed_segments(request, current_requirements, snapshot)
        if proposed_rows is None:
            return delta(
                demand_number=demand_number,
                available=False,
                reason="PROPOSAL_INCOMPLETE",
                has_changes=False,
            )

        remaining_segments = [
            row
            for row in snapshot.segments
            if _text(row.get("NoDemande")) != demand_number
        ]
        proposed_snapshot = PlanningSnapshot.capture(
            segments=[*remaining_segments, *proposed_rows],
            demands=snapshot.demands,
            allocations=snapshot.allocations,
            availability=snapshot.availability,
            technicians=snapshot.technicians,
        )
        proposed_calculation = project_planning_snapshot(proposed_snapshot)
        if proposed_calculation.unsupported_segment_ids:
            return delta(
                demand_number=demand_number,
                available=False,
                reason="PROPOSED_PLAN_UNSUPPORTED",
                has_changes=False,
            )

        proposed_result = build_allocation_plan(
            proposed_calculation.segments,
            proposed_calculation.locked_allocations,
            proposed_calculation.capacity_by_resource_day,
            preserve_locked_segment_ids=proposed_calculation.preserved_segment_ids,
            outside_schedule_eligible_by_resource_day=(
                proposed_calculation.outside_schedule_eligible_by_resource_day
            ),
        )
        comparison = compare_allocation_plans(
            current_calculation.persisted_allocations,
            _allocation_projection(proposed_result),
        )
        resource_id_by_name = {
            resource.name: resource.id
            for resource in self._delta_session.scalars(select(Resource)).all()
        }
        items = _delta_items(
            comparison.differences,
            resource_id_by_name=resource_id_by_name,
        )
        counts = {
            name: sum(1 for item in items if item.change == name)
            for name in ("ADD", "MODIFY", "MOVE", "CANCEL")
        }
        current_hours = round(sum(item.current_hours for item in items), 2)
        proposed_hours = round(sum(item.proposed_hours for item in items), 2)
        return delta(
            demand_number=demand_number,
            available=True,
            reason=None,
            has_changes=bool(items),
            add_count=counts["ADD"],
            modify_count=counts["MODIFY"],
            move_count=counts["MOVE"],
            cancel_count=counts["CANCEL"],
            current_hours=current_hours,
            proposed_hours=proposed_hours,
            net_hours=round(proposed_hours - current_hours, 2),
            items=items,
        )
