from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...application.plan_delta import (
    DemandPlanDeltaItemReadModel,
    DemandPlanDeltaReadModel,
)
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
from .demand_period_models import (
    WorkforceRequestPeriod,
    WorkforceRequestPeriodRequirement,
    WorkforceRequestPeriodSelection,
)
from .models import Project, Resource, ResourceRequirement, WorkforceRequest
from .planning_repository import SqlPlanningReadRepository
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
    )


def _item_from_difference(
    difference: AllocationDifference,
    *,
    change: str,
) -> DemandPlanDeltaItemReadModel:
    current = difference.legacy_hours > 0
    proposed = difference.shadow_hours > 0
    return DemandPlanDeltaItemReadModel(
        change=change,
        segment_id=difference.segment_id,
        current_resource_name=difference.resource_id if current else None,
        proposed_resource_name=difference.resource_id if proposed else None,
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
) -> tuple[DemandPlanDeltaItemReadModel, ...]:
    """Turn semantic-key differences into coordinator-friendly add/move/change/cancel rows."""

    direct: list[DemandPlanDeltaItemReadModel] = []
    old_only: dict[str, list[AllocationDifference]] = defaultdict(list)
    new_only: dict[str, list[AllocationDifference]] = defaultdict(list)

    for difference in differences:
        if difference.legacy_hours > 0 and difference.shadow_hours > 0:
            direct.append(_item_from_difference(difference, change="MODIFY"))
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
                direct.append(_item_from_difference(old, change="CANCEL"))
                continue
            new = new_rows[pair_index]
            used_new.add(pair_index)
            direct.append(
                DemandPlanDeltaItemReadModel(
                    change="MOVE",
                    segment_id=segment_id,
                    current_resource_name=old.resource_id,
                    proposed_resource_name=new.resource_id,
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
                direct.append(_item_from_difference(new, change="ADD"))

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

    def _effective_periods(self, request_id: str) -> list[WorkforceRequestPeriod]:
        periods = list(
            self._delta_session.scalars(
                select(WorkforceRequestPeriod)
                .where(
                    WorkforceRequestPeriod.workforce_request_id == request_id,
                    WorkforceRequestPeriod.active.is_(True),
                )
                .order_by(WorkforceRequestPeriod.sequence, WorkforceRequestPeriod.id)
            ).all()
        )
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

    def _proposed_segments(
        self,
        request: WorkforceRequest,
        current: list[ResourceRequirement],
        snapshot: PlanningSnapshot,
    ) -> list[dict[str, object]] | None:
        project = self._delta_session.get(Project, request.project_id)
        if project is None:
            return None
        resources = {
            row.id: row
            for row in self._delta_session.scalars(select(Resource)).all()
        }
        period_key_by_requirement = self._period_key_by_requirement(request.id)
        periods = self._effective_periods(request.id)
        proposed: list[dict[str, object]] = []

        if periods:
            current_by_period: dict[str, list[ResourceRequirement]] = defaultdict(list)
            for requirement in current:
                key = period_key_by_requirement.get(requirement.id)
                if key:
                    current_by_period[key].append(requirement)

            for period in periods:
                ranked = sorted(
                    current_by_period.get(period.period_key, []),
                    key=lambda row: (
                        0 if row.assigned_resource_id else 1,
                        row.created_at,
                        row.id,
                    ),
                )
                desired = max(int(period.resource_count or 1), 1)
                inherited_confirmation = normalize_confirmation(period.confirmation)
                for index in range(desired):
                    requirement = ranked[index] if index < len(ranked) else None
                    resource = (
                        resources.get(requirement.assigned_resource_id)
                        if requirement is not None and requirement.assigned_resource_id
                        else resources.get(period.proposed_resource_id)
                    )
                    proposed.append(
                        self._segment_row(
                            requirement=requirement,
                            request=request,
                            project=project,
                            resource=resource,
                            start_date=period.start_date,
                            end_date=period.end_date,
                            hours=float(period.hours),
                            confirmation=inherited_confirmation,
                            description=period.note or request.description,
                            synthetic_id=f"PREVIEW-{period.period_key}-{index + 1}",
                        )
                    )
            return proposed

        if request.desired_start is None:
            return None
        desired = max(int(request.resource_count or 1), 1)
        proposed_resource = resources.get(request.proposed_resource_id)
        per_resource = self._legacy_hours_per_resource(
            request,
            desired,
            current,
            proposed_resource,
            snapshot,
        )
        if per_resource is None or per_resource <= 0:
            return None
        ranked = sorted(
            current,
            key=lambda row: (
                0 if row.assigned_resource_id else 1,
                row.created_at,
                row.id,
            ),
        )
        inherited_confirmation = normalize_confirmation(
            request.confirmation,
            default=CONFIRMATION_CONFIRMED,
        )
        for index in range(desired):
            requirement = ranked[index] if index < len(ranked) else None
            if requirement is not None and requirement.assigned_resource_id:
                resource = resources.get(requirement.assigned_resource_id)
            elif index == 0:
                resource = proposed_resource
            else:
                resource = None
            proposed.append(
                self._segment_row(
                    requirement=requirement,
                    request=request,
                    project=project,
                    resource=resource,
                    start_date=request.desired_start,
                    end_date=request.desired_end or request.desired_start,
                    hours=per_resource,
                    confirmation=inherited_confirmation,
                    description=request.description or "Ressource additionnelle",
                    synthetic_id=f"PREVIEW-{request.id}-{index + 1}",
                )
            )
        return proposed

    def demand_plan_delta(self, number: str) -> DemandPlanDeltaReadModel | None:
        request = self._request(number)
        if request is None:
            return None
        demand_number = _text(request.legacy_demand_number) or request.id
        current_requirements = self._current_requirements(request.id)
        if request.status != "Soumise":
            return DemandPlanDeltaReadModel(
                demand_number=demand_number,
                available=False,
                reason="NOT_SUBMITTED",
                has_changes=False,
            )
        if not current_requirements:
            return DemandPlanDeltaReadModel(
                demand_number=demand_number,
                available=False,
                reason="NO_CURRENT_PLAN",
                has_changes=False,
            )

        snapshot = SqlPlanningReadRepository(self._delta_session).capture()
        current_calculation = project_planning_snapshot(snapshot)
        if current_calculation.unsupported_segment_ids:
            return DemandPlanDeltaReadModel(
                demand_number=demand_number,
                available=False,
                reason="CURRENT_PLAN_UNSUPPORTED",
                has_changes=False,
            )

        proposed_rows = self._proposed_segments(request, current_requirements, snapshot)
        if proposed_rows is None:
            return DemandPlanDeltaReadModel(
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
            return DemandPlanDeltaReadModel(
                demand_number=demand_number,
                available=False,
                reason="PROPOSED_PLAN_UNSUPPORTED",
                has_changes=False,
            )

        proposed_result = build_allocation_plan(
            proposed_calculation.segments,
            proposed_calculation.locked_allocations,
            proposed_calculation.capacity_by_resource_day,
            outside_schedule_eligible_by_resource_day=(
                proposed_calculation.outside_schedule_eligible_by_resource_day
            ),
        )
        comparison = compare_allocation_plans(
            current_calculation.persisted_allocations,
            _allocation_projection(proposed_result),
        )
        items = _delta_items(comparison.differences)
        counts = {
            name: sum(1 for item in items if item.change == name)
            for name in ("ADD", "MODIFY", "MOVE", "CANCEL")
        }
        current_hours = round(sum(item.current_hours for item in items), 2)
        proposed_hours = round(sum(item.proposed_hours for item in items), 2)
        return DemandPlanDeltaReadModel(
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
