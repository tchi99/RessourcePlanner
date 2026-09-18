from __future__ import annotations

from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ...application.query_models import (
    PendingDemandLoadReadModel,
    PlanningSnapshotReadModel,
    ProjectReadModel,
    ResourceReadModel,
    ShiftReadModel,
)
from ...application.query_ports import PlannerQueryPort
from ...application.read_models import DemandPeriodReadModel, DemandReadModel, SegmentReadModel
from ...domain.confirmation import effective_confirmation
from ...domain.demand_periods import (
    DemandPeriodDefinition,
    projected_hours_in_window,
    projected_hours_without_double_counting,
    projected_period_hours_in_window_without_double_counting,
)
from ...domain.workload import (
    PENDING_LOAD_ADDITIVE,
    WorkloadTotals,
    pending_load_mode,
    workload_kind,
)
from .demand_period_repository import SqlDemandPeriodRepository
from .demand_repository import SqlDemandRepository
from .models import (
    Project,
    Resource,
    ResourceAvailabilityRule,
    ResourceCompetency,
    ResourceRequirement,
    Shift,
    WorkforceRequest,
)
from .segment_repository import SqlSegmentRepository


INACTIVE_PROJECT_STATUSES = {
    "annulé",
    "annule",
    "fermé",
    "ferme",
    "terminé",
    "termine",
    "closed",
    "cancelled",
}


def _text(value: object) -> str:
    return str(value or "").strip()


def _optional_text(value: object) -> str | None:
    value_text = _text(value)
    return value_text or None


def _demand_overlaps(row: DemandReadModel, start: date, end: date) -> bool:
    if row.desired_end is not None and row.desired_end < start:
        return False
    if row.desired_start is not None and row.desired_start > end:
        return False
    return True


def _period_definition(row: DemandPeriodReadModel) -> DemandPeriodDefinition:
    return DemandPeriodDefinition(
        period_id=row.period_id,
        start_date=row.start_date,
        end_date=row.end_date,
        hours=row.hours,
        kind=row.kind,
        alternative_group=row.alternative_group,
        confirmation=row.confirmation,
        proposed_resource=row.proposed_resource,
        resource_count=row.resource_count,
        note=row.note,
    )


def _resource_read_model(resource: Resource, competency_ids: tuple[str, ...] = ()) -> ResourceReadModel:
    return ResourceReadModel(
        id=resource.id,
        name=resource.name,
        email=_optional_text(resource.email),
        resource_class=_optional_text(resource.resource_class),
        competencies=_optional_text(resource.competencies),
        competency_ids=competency_ids,
        note=_optional_text(resource.note),
        active=bool(resource.active),
        sort_order=int(resource.sort_order or 0),
        external_id=_optional_text(resource.external_id),
    )


class SqlPlannerQueryRepository(PlannerQueryPort):
    """Read-only SQL projection for the future web frontend."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._demands = SqlDemandRepository(session)
        self._periods = SqlDemandPeriodRepository(session)
        self._segments = SqlSegmentRepository(session)

    def _resource_competency_ids(self, resource_id: str) -> tuple[str, ...]:
        return tuple(
            self._session.scalars(
                select(ResourceCompetency.competency_id).where(
                    ResourceCompetency.resource_id == resource_id
                )
            ).all()
        )

    def list_projects(self, *, active_only: bool = False) -> tuple[ProjectReadModel, ...]:
        rows = self._session.scalars(select(Project).order_by(Project.number)).all()
        result: list[ProjectReadModel] = []
        for project in rows:
            status = _text(project.status) or "active"
            active = status.casefold() not in INACTIVE_PROJECT_STATUSES
            if active_only and not active:
                continue
            result.append(
                ProjectReadModel(
                    id=project.id,
                    number=project.number,
                    name=project.name,
                    client=_optional_text(project.client),
                    project_manager=_optional_text(project.project_manager_name),
                    status=status,
                    active=active,
                    erp_external_id=_optional_text(project.erp_external_id),
                )
            )
        return tuple(result)

    def list_resources(self, *, active_only: bool = True) -> tuple[ResourceReadModel, ...]:
        statement = select(Resource)
        if active_only:
            statement = statement.where(Resource.active.is_(True))
        rows = self._session.scalars(
            statement.order_by(Resource.sort_order, Resource.name)
        ).all()
        return tuple(_resource_read_model(resource, self._resource_competency_ids(resource.id)) for resource in rows)

    def list_schedulable_resources(
        self,
        *,
        start: date,
        end: date,
    ) -> tuple[ResourceReadModel, ...]:
        """Return active resources whose standard-schedule envelope overlaps the window."""

        if end < start:
            start, end = end, start
        scheduled_ids = select(ResourceAvailabilityRule.resource_id).where(
            ResourceAvailabilityRule.availability_type == "Horaire standard",
            ResourceAvailabilityRule.active.is_(True),
            ResourceAvailabilityRule.resource_id.is_not(None),
            or_(
                ResourceAvailabilityRule.start_date.is_(None),
                ResourceAvailabilityRule.start_date <= end,
            ),
            or_(
                ResourceAvailabilityRule.end_date.is_(None),
                ResourceAvailabilityRule.end_date >= start,
            ),
        )
        rows = self._session.scalars(
            select(Resource)
            .where(
                Resource.active.is_(True),
                Resource.id.in_(scheduled_ids),
            )
            .order_by(Resource.sort_order, Resource.name)
        ).all()
        return tuple(_resource_read_model(resource) for resource in rows)

    def list_demands(self) -> tuple[DemandReadModel, ...]:
        return tuple(self._demands.list())

    def get_demand(self, number: str) -> DemandReadModel | None:
        return self._demands.get(number)

    def list_demand_periods(self, number: str) -> tuple[DemandPeriodReadModel, ...]:
        return tuple(self._periods.list_for_demand(number))

    def list_pending_loads(
        self,
        *,
        start: date,
        end: date,
    ) -> tuple[PendingDemandLoadReadModel, ...]:
        """Project submitted requests without mutating or double-counting approved work."""

        requests = self._session.scalars(
            select(WorkforceRequest)
            .where(WorkforceRequest.status == "Soumise")
            .order_by(
                WorkforceRequest.desired_start,
                WorkforceRequest.legacy_demand_number,
                WorkforceRequest.id,
            )
        ).all()
        result: list[PendingDemandLoadReadModel] = []

        for request in requests:
            number = _text(request.legacy_demand_number) or request.id
            demand = self._demands.get(number)
            if demand is None:
                continue

            periods = tuple(self._periods.list_for_demand(number))
            if periods:
                definitions = tuple(_period_definition(row) for row in periods)
                selections = {
                    _text(row.alternative_group): row.period_id
                    for row in periods
                    if row.selected and _text(row.alternative_group)
                }
                proposal_start = min(row.start_date for row in periods)
                proposal_end = max(row.end_date for row in periods)
                if proposal_end < start or proposal_start > end:
                    continue
                projected_hours = projected_hours_without_double_counting(
                    definitions,
                    selections,
                )
                window_hours = projected_period_hours_in_window_without_double_counting(
                    definitions,
                    start,
                    end,
                    selections,
                )
            else:
                proposal_start = demand.desired_start
                if proposal_start is None:
                    continue
                proposal_end = demand.desired_end or proposal_start
                if proposal_end < start or proposal_start > end:
                    continue
                projected_hours = demand.estimated_hours
                window_hours = (
                    projected_hours_in_window(
                        projected_hours,
                        proposal_start,
                        proposal_end,
                        start,
                        end,
                    )
                    if projected_hours is not None
                    else 0.0
                )

            current = self._session.scalars(
                select(ResourceRequirement).where(
                    ResourceRequirement.workforce_request_id == request.id,
                    ResourceRequirement.status != "Annulé",
                )
            ).all()
            current_plan_hours = round(
                sum(
                    projected_hours_in_window(
                        float(requirement.planned_hours),
                        requirement.start_date,
                        requirement.end_date,
                        start,
                        end,
                    )
                    for requirement in current
                ),
                2,
            )
            mode = pending_load_mode(has_current_plan=bool(current))
            delta_hours = (
                round(window_hours - current_plan_hours, 2)
                if projected_hours is not None
                else None
            )
            result.append(
                PendingDemandLoadReadModel(
                    demand_number=number,
                    project_number=demand.project_number,
                    project_name=demand.project_name,
                    start_date=proposal_start,
                    end_date=proposal_end,
                    projected_hours=projected_hours,
                    window_hours=window_hours,
                    mode=mode,
                    current_plan_hours=current_plan_hours,
                    delta_hours=delta_hours,
                    resource_count=demand.resource_count,
                    required_competencies=demand.required_competencies,
                    proposed_resource=demand.proposed_resource,
                    work_package_ref=demand.work_package_ref,
                    confirmation=demand.confirmation,
                    periods=periods,
                )
            )

        return tuple(result)

    def list_segments(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
        include_cancelled: bool = False,
    ) -> tuple[SegmentReadModel, ...]:
        rows = self._segments.list(include_cancelled=include_cancelled)
        result: list[SegmentReadModel] = []
        for row in rows:
            if start is not None and row.end_date is not None and row.end_date < start:
                continue
            if end is not None and row.start_date is not None and row.start_date > end:
                continue
            result.append(row)
        return tuple(result)

    def get_segment(self, segment_id: str) -> SegmentReadModel | None:
        return self._segments.get(segment_id)

    def list_shifts(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
        resource_name: str | None = None,
        resource_id: str | None = None,
    ) -> tuple[ShiftReadModel, ...]:
        statement = (
            select(Shift, ResourceRequirement, Resource, Project, WorkforceRequest)
            .join(
                ResourceRequirement,
                Shift.resource_requirement_id == ResourceRequirement.id,
            )
            .join(Resource, Shift.resource_id == Resource.id)
            .join(Project, ResourceRequirement.project_id == Project.id)
            .outerjoin(
                WorkforceRequest,
                ResourceRequirement.workforce_request_id == WorkforceRequest.id,
            )
        )
        if start is not None:
            statement = statement.where(Shift.work_date >= start)
        if end is not None:
            statement = statement.where(Shift.work_date <= end)
        wanted_resource = _text(resource_name)
        if wanted_resource:
            statement = statement.where(Resource.name == wanted_resource)
        wanted_resource_id = _text(resource_id)
        if wanted_resource_id:
            statement = statement.where(Resource.id == wanted_resource_id)

        rows = self._session.execute(
            statement.order_by(
                Shift.work_date,
                Resource.sort_order,
                Resource.name,
                Shift.locked.desc(),
                Shift.id,
            )
        ).all()
        result: list[ShiftReadModel] = []
        for shift, requirement, resource, project, request in rows:
            confirmation = effective_confirmation(
                shift.confirmation,
                requirement.confirmation,
            )
            result.append(
                ShiftReadModel(
                    allocation_id=_text(shift.legacy_allocation_id) or shift.id,
                    segment_id=_text(requirement.legacy_segment_id) or requirement.id,
                    resource_id=resource.id,
                    resource_name=resource.name,
                    work_date=shift.work_date,
                    hours=float(shift.hours),
                    allocation_type=_optional_text(shift.allocation_type),
                    source=_text(shift.source) or "AUTO",
                    locked=bool(shift.locked),
                    outside_standard_hours=bool(shift.outside_standard_hours),
                    confirmation=confirmation,
                    confirmation_override=_optional_text(shift.confirmation),
                    load_kind=workload_kind(confirmation),
                    note=_optional_text(shift.note),
                    demand_number=(
                        _text(request.legacy_demand_number) or request.id
                        if request is not None
                        else None
                    ),
                    project_number=_optional_text(project.number),
                    project_name=_optional_text(project.name),
                    project_manager=_optional_text(project.project_manager_name),
                    requester=(
                        _optional_text(request.requester_name)
                        if request is not None
                        else _optional_text(requirement.created_by_name)
                    ),
                )
            )
        return tuple(result)

    def planning_snapshot(
        self,
        *,
        start: date,
        end: date,
    ) -> PlanningSnapshotReadModel:
        """Read the web planning window inside the caller-owned SQL transaction."""

        demands = tuple(
            row for row in self.list_demands() if _demand_overlaps(row, start, end)
        )
        shifts = self.list_shifts(start=start, end=end)
        pending_loads = self.list_pending_loads(start=start, end=end)
        totals = WorkloadTotals()
        for shift in shifts:
            totals = totals.add(shift.hours, shift.confirmation)
        additive_pending = round(
            sum(
                row.window_hours
                for row in pending_loads
                if row.mode == PENDING_LOAD_ADDITIVE
            ),
            2,
        )
        replacement_proposals = round(
            sum(
                row.window_hours
                for row in pending_loads
                if row.mode != PENDING_LOAD_ADDITIVE
            ),
            2,
        )
        return PlanningSnapshotReadModel(
            start=start,
            end=end,
            resources=self.list_schedulable_resources(start=start, end=end),
            demands=demands,
            segments=self.list_segments(start=start, end=end, include_cancelled=False),
            shifts=shifts,
            pending_loads=pending_loads,
            firm_hours=totals.firm_hours,
            potential_hours=round(totals.potential_hours + additive_pending, 2),
            replacement_proposal_hours=replacement_proposals,
        )
