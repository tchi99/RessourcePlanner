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


def _resource_read_model(resource: Resource) -> ResourceReadModel:
    return ResourceReadModel(
        id=resource.id,
        name=resource.name,
        email=_optional_text(resource.email),
        resource_class=_optional_text(resource.resource_class),
        competencies=_optional_text(resource.competencies),
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
        return tuple(_resource_read_model(resource) for resource in rows)

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
        if end < start:
            start, end = end, start
        demands = self._demands.list()
        periods_by_demand: dict[str, list[DemandPeriodReadModel]] = {}
        selections_by_demand: dict[str, dict[str, str]] = {}
        segments_by_demand: dict[str, list[SegmentReadModel]] = {}
        for segment in self._segments.list(include_cancelled=False):
            if segment.demand_number:
                segments_by_demand.setdefault(segment.demand_number, []).append(segment)
        result: list[PendingDemandLoadReadModel] = []
        for demand in demands:
            if demand.status != "Soumise" or not _demand_overlaps(demand, start, end):
                continue
            periods = periods_by_demand.setdefault(
                demand.number,
                list(self._periods.list_for_demand(demand.number)),
            )
            definitions = tuple(_period_definition(period) for period in periods)
            selections = selections_by_demand.setdefault(
                demand.number,
                dict(self._periods.selections_for_demand(demand.number)),
            )
            projected_hours = (
                projected_period_hours_in_window_without_double_counting(
                    definitions,
                    start,
                    end,
                    selections=selections,
                )
                if definitions
                else projected_hours_in_window(
                    start=demand.desired_start,
                    end=demand.desired_end,
                    hours=demand.estimated_hours,
                    window_start=start,
                    window_end=end,
                )
            )
            window_hours = (
                projected_hours_without_double_counting(definitions, selections=selections)
                if definitions
                else float(demand.estimated_hours or 0.0)
            )
            current_plan_hours = sum(
                segment.planned_hours
                for segment in segments_by_demand.get(demand.number, ())
                if segment.status != "Annulé"
            )
            mode = pending_load_mode(current_plan_hours=current_plan_hours)
            result.append(
                PendingDemandLoadReadModel(
                    demand_number=demand.number,
                    project_number=demand.project_number,
                    project_name=demand.project_name,
                    start_date=demand.desired_start or start,
                    end_date=demand.desired_end or demand.desired_start or end,
                    projected_hours=projected_hours,
                    window_hours=window_hours,
                    mode=mode,
                    load_kind=workload_kind(demand.confirmation),
                    current_plan_hours=current_plan_hours,
                    delta_hours=(
                        projected_hours - current_plan_hours
                        if mode != PENDING_LOAD_ADDITIVE
                        else None
                    ),
                    resource_count=demand.resource_count,
                    confirmation=demand.confirmation,
                    required_competencies=demand.required_competencies,
                    proposed_resource=demand.proposed_technician,
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
        if start is None and end is None:
            return tuple(rows)
        return tuple(
            row
            for row in rows
            if not (
                (start is not None and row.end_date < start)
                or (end is not None and row.start_date > end)
            )
        )

    def get_segment(self, segment_id: str) -> SegmentReadModel | None:
        return self._segments.get(segment_id)

    def list_shifts(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
        resource_name: str | None = None,
    ) -> tuple[ShiftReadModel, ...]:
        statement = (
            select(Shift, Resource, ResourceRequirement, WorkforceRequest, Project)
            .join(Resource, Shift.resource_id == Resource.id)
            .join(ResourceRequirement, Shift.resource_requirement_id == ResourceRequirement.id)
            .outerjoin(WorkforceRequest, ResourceRequirement.workforce_request_id == WorkforceRequest.id)
            .join(Project, ResourceRequirement.project_id == Project.id)
            .order_by(Shift.work_date, Resource.sort_order, Resource.name, Shift.id)
        )
        if start is not None:
            statement = statement.where(Shift.work_date >= start)
        if end is not None:
            statement = statement.where(Shift.work_date <= end)
        if resource_name:
            statement = statement.where(Resource.name == resource_name)
        rows = self._session.execute(statement).all()
        result: list[ShiftReadModel] = []
        for shift, resource, requirement, demand, project in rows:
            result.append(
                ShiftReadModel(
                    allocation_id=shift.id,
                    segment_id=requirement.id,
                    resource_id=resource.id,
                    resource_name=resource.name,
                    work_date=shift.work_date,
                    hours=float(shift.hours),
                    allocation_type=_optional_text(shift.allocation_type),
                    source=_text(shift.source) or "AUTO",
                    locked=bool(shift.locked),
                    outside_standard_hours=bool(shift.outside_standard_hours),
                    confirmation=effective_confirmation(
                        shift.confirmation_override,
                        requirement.confirmation,
                    ),
                    confirmation_override=_optional_text(shift.confirmation_override),
                    load_kind=workload_kind(
                        effective_confirmation(
                            shift.confirmation_override,
                            requirement.confirmation,
                        )
                    ),
                    note=_optional_text(shift.note),
                    demand_number=(
                        _optional_text(demand.legacy_demand_number)
                        if demand is not None
                        else None
                    ),
                    project_number=project.number,
                    project_name=project.name,
                    project_manager=_optional_text(project.project_manager_name),
                    requester=(
                        _optional_text(demand.requester_name) if demand is not None else None
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
        if end < start:
            start, end = end, start
        resources = self.list_schedulable_resources(start=start, end=end)
        shifts = self.list_shifts(start=start, end=end)
        pending = self.list_pending_loads(start=start, end=end)
        totals = WorkloadTotals.from_inputs(shifts=shifts, pending_loads=pending)
        return PlanningSnapshotReadModel(
            start_date=start,
            end_date=end,
            resources=resources,
            shifts=shifts,
            pending_loads=pending,
            firm_hours=totals.firm_hours,
            potential_hours=totals.potential_hours,
            replacement_proposal_hours=totals.replacement_proposal_hours,
        )
