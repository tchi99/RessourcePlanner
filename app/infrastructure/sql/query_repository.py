from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
import unicodedata

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ...application.query_models import (
    MediumTermUnlinkedSegmentReadModel,
    PendingDemandLoadReadModel,
    PlanningActionReadModel,
    PlanningCapacityGridReadModel,
    PlanningDayCapacityReadModel,
    PlanningResourceCapacityReadModel,
    PlanningSegmentCapacityDiagnosticReadModel,
    PlanningSnapshotReadModel,
    ProjectReadModel,
    ResourceReadModel,
    ResourceRecommendationReadModel,
    ShiftReadModel,
)
from ...application.query_ports import PlannerQueryPort
from ...application.read_models import DemandPeriodReadModel, DemandReadModel, SegmentReadModel
from ...domain.availability_rules import availability_hours_for_day, availability_state_for_day
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
    Competency,
    Project,
    Resource,
    ResourceAvailabilityRule,
    ResourceCompetency,
    ResourceRequirement,
    Shift,
    WorkforceRequest,
    WorkPackage,
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


def _normalized_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", _text(value)).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.casefold().split())


def _resource_class_hint(value: object) -> str | None:
    text = _normalized_text(value)
    if not text:
        return None
    if "programm" in text or "automatis" in text:
        return "Programmation"
    if "installation" in text or "installateur" in text:
        return "Installation"
    if ("monteur" in text and "panneau" in text) or (
        "panel" in text and ("builder" in text or "wire" in text)
    ):
        return "Monteur de panneau"
    if "dessin" in text or "draft" in text or "cad" in text:
        return "Dessinateur"
    if ("gestion" in text and "projet" in text) or (
        "charge" in text and "projet" in text
    ):
        return "Gestion de projet"
    return None


def _split_competencies(value: object) -> tuple[str, ...]:
    raw = _text(value)
    if not raw:
        return ()
    return tuple(
        part.strip()
        for part in raw.replace(",", ";").split(";")
        if part.strip()
    )


def _availability_record(rule: ResourceAvailabilityRule) -> dict[str, object]:
    return {
        "Type": rule.availability_type,
        "Actif": bool(rule.active),
        "Technicien": rule.resource_id or "",
        "DateDebut": rule.start_date,
        "DateFin": rule.end_date,
        "JoursSemaine": rule.weekdays,
        "HeureDebut": rule.start_time,
        "HeureFin": rule.end_time,
    }


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

    def _resource_competency_ids_by_resource(
        self,
        resource_ids: Sequence[str],
    ) -> dict[str, tuple[str, ...]]:
        identifiers = tuple(str(value) for value in resource_ids if str(value))
        if not identifiers:
            return {}
        grouped: dict[str, list[str]] = {identifier: [] for identifier in identifiers}
        rows = self._session.execute(
            select(
                ResourceCompetency.resource_id,
                ResourceCompetency.competency_id,
            )
            .where(ResourceCompetency.resource_id.in_(identifiers))
            .order_by(
                ResourceCompetency.resource_id,
                ResourceCompetency.competency_id,
            )
        ).all()
        for resource_id, competency_id in rows:
            grouped.setdefault(resource_id, []).append(competency_id)
        return {
            resource_id: tuple(competency_ids)
            for resource_id, competency_ids in grouped.items()
        }

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
        competency_ids = self._resource_competency_ids_by_resource(
            tuple(resource.id for resource in rows)
        )
        return tuple(
            _resource_read_model(resource, competency_ids.get(resource.id, ()))
            for resource in rows
        )

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
        competency_ids = self._resource_competency_ids_by_resource(
            tuple(resource.id for resource in rows)
        )
        return tuple(
            _resource_read_model(resource, competency_ids.get(resource.id, ()))
            for resource in rows
        )

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
        demands_by_number = {
            demand.number: demand
            for demand in self._demands.list()
        }

        for request in requests:
            number = _text(request.legacy_demand_number) or request.id
            demand = demands_by_number.get(number)
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

    def list_medium_term_unlinked_segments(
        self,
        *,
        start: date,
        end: date,
    ) -> tuple[MediumTermUnlinkedSegmentReadModel, ...]:
        """Expose active segments with no valid medium-term WorkPackage classification."""

        if end < start:
            start, end = end, start

        rows = self._session.execute(
            select(ResourceRequirement, Project, WorkforceRequest, Resource)
            .join(Project, ResourceRequirement.project_id == Project.id)
            .outerjoin(
                WorkforceRequest,
                ResourceRequirement.workforce_request_id == WorkforceRequest.id,
            )
            .outerjoin(Resource, ResourceRequirement.assigned_resource_id == Resource.id)
            .where(
                ResourceRequirement.status.notin_(("Annulé", "Terminé")),
                ResourceRequirement.end_date >= start,
                ResourceRequirement.start_date <= end,
            )
            .order_by(
                ResourceRequirement.start_date,
                Project.number,
                ResourceRequirement.legacy_segment_id,
                ResourceRequirement.id,
            )
        ).all()
        work_packages = self._session.scalars(select(WorkPackage)).all()
        package_by_reference: dict[str, WorkPackage] = {}
        package_by_id: dict[str, WorkPackage] = {}
        for package in work_packages:
            package_by_id[package.id] = package
            package_by_reference[package.id] = package
            legacy = _text(package.legacy_effort_id)
            if legacy:
                package_by_reference[legacy] = package

        result: list[MediumTermUnlinkedSegmentReadModel] = []
        for requirement, project, request, resource in rows:
            segment_id = _text(requirement.legacy_segment_id) or requirement.id
            origin = _text(requirement.origin) or "REQUEST"
            current_ref = _optional_text(requirement.source_effort_id)

            if request is not None and request.work_package_id:
                package = package_by_id.get(request.work_package_id)
                if package is not None:
                    continue
                classification = "BROKEN_REFERENCE"
                anomaly = True
                link_target = "DEMAND"
            elif request is not None:
                classification = "REQUEST_UNLINKED"
                anomaly = True
                link_target = "DEMAND"
            else:
                linked_package = package_by_reference.get(current_ref or "")
                if linked_package is not None and linked_package.project_id == project.id:
                    continue
                if current_ref:
                    classification = "BROKEN_REFERENCE"
                    anomaly = True
                elif origin in {"QUICK_SHIFT", "AD_HOC"}:
                    classification = "AD_HOC_ALLOWED"
                    anomaly = False
                else:
                    classification = "ORPHAN_SEGMENT"
                    anomaly = True
                link_target = "SEGMENT"

            demand_number = (
                _text(request.legacy_demand_number) or request.id
                if request is not None
                else None
            )
            result.append(
                MediumTermUnlinkedSegmentReadModel(
                    segment_id=segment_id,
                    demand_number=demand_number,
                    project_number=project.number,
                    project_name=project.name,
                    task_code=_optional_text(request.erp_task_code) if request is not None else None,
                    task_label=_optional_text(request.erp_task_label) if request is not None else None,
                    start_date=requirement.start_date,
                    end_date=requirement.end_date,
                    planned_hours=float(requirement.planned_hours),
                    resource_name=_optional_text(resource.name) if resource is not None else None,
                    status=_text(requirement.status),
                    origin=origin,
                    classification=classification,
                    anomaly=anomaly,
                    link_target=link_target,
                    current_work_package_ref=current_ref,
                    reapproval_on_link=(
                        request is not None and request.status == "En planification"
                    ),
                    description=_optional_text(requirement.description),
                )
            )
        return tuple(result)

    def planning_capacity_grid(
        self,
        *,
        start: date,
        end: date,
    ) -> PlanningCapacityGridReadModel:
        """Return backend-authoritative daily/weekly capacity diagnostics for React."""

        if end < start:
            start, end = end, start
        resources = self.list_schedulable_resources(start=start, end=end)
        rules = self._session.scalars(
            select(ResourceAvailabilityRule).where(ResourceAvailabilityRule.active.is_(True))
        ).all()
        availability = tuple(_availability_record(rule) for rule in rules)
        shifts = self.list_shifts(start=start, end=end)

        shifts_by_resource_day: dict[tuple[str, date], list[ShiftReadModel]] = {}
        shifts_by_segment: dict[str, list[ShiftReadModel]] = {}
        for shift in shifts:
            shifts_by_resource_day.setdefault((shift.resource_id, shift.work_date), []).append(shift)
            shifts_by_segment.setdefault(shift.segment_id, []).append(shift)

        resource_rows: list[PlanningResourceCapacityReadModel] = []
        for resource in resources:
            day_rows: list[PlanningDayCapacityReadModel] = []
            cursor = start
            while cursor <= end:
                state = availability_state_for_day(availability, resource.id, cursor)
                own = shifts_by_resource_day.get((resource.id, cursor), [])
                confirmed = 0.0
                tentative = 0.0
                outside = 0.0
                for shift in own:
                    amount = float(shift.hours)
                    if shift.outside_standard_hours:
                        outside += amount
                    elif shift.load_kind == "FIRM":
                        confirmed += amount
                    else:
                        tentative += amount
                total = confirmed + tentative + outside
                prudent_free = max(float(state.hours) - confirmed - tentative, 0.0)
                overloaded = confirmed + tentative > float(state.hours) + 0.01
                day_rows.append(
                    PlanningDayCapacityReadModel(
                        day=cursor,
                        capacity_hours=round(float(state.hours), 2),
                        confirmed_hours=round(confirmed, 2),
                        tentative_hours=round(tentative, 2),
                        outside_standard_hours=round(outside, 2),
                        total_hours=round(total, 2),
                        prudent_free=round(prudent_free, 2),
                        available=bool(state.available),
                        overloaded=overloaded,
                        reason=state.reason,
                    )
                )
                cursor += timedelta(days=1)

            capacity = round(sum(row.capacity_hours for row in day_rows), 2)
            confirmed = round(sum(row.confirmed_hours for row in day_rows), 2)
            tentative = round(sum(row.tentative_hours for row in day_rows), 2)
            outside = round(sum(row.outside_standard_hours for row in day_rows), 2)
            resource_rows.append(
                PlanningResourceCapacityReadModel(
                    resource_id=resource.id,
                    resource_name=resource.name,
                    resource_class=resource.resource_class,
                    capacity_hours=capacity,
                    confirmed_hours=confirmed,
                    tentative_hours=tentative,
                    outside_standard_hours=outside,
                    prudent_free=round(max(capacity - confirmed - tentative, 0.0), 2),
                    overloaded=any(row.overloaded for row in day_rows),
                    days=tuple(day_rows),
                )
            )

        requirements = self._session.execute(
            select(ResourceRequirement, Resource)
            .outerjoin(Resource, ResourceRequirement.assigned_resource_id == Resource.id)
            .where(
                ResourceRequirement.status.notin_(("Annulé", "Terminé")),
                ResourceRequirement.end_date >= start,
                ResourceRequirement.start_date <= end,
                ResourceRequirement.assigned_resource_id.is_not(None),
            )
            .order_by(ResourceRequirement.start_date, ResourceRequirement.id)
        ).all()
        requirement_ids = tuple(requirement.id for requirement, _ in requirements)
        full_shift_totals: dict[str, tuple[float, float]] = {}
        if requirement_ids:
            raw_shift_rows = self._session.execute(
                select(
                    Shift.resource_requirement_id,
                    Shift.hours,
                    Shift.outside_standard_hours,
                ).where(Shift.resource_requirement_id.in_(requirement_ids))
            ).all()
            accumulated: dict[str, list[float]] = {}
            for requirement_id, shift_hours, outside_flag in raw_shift_rows:
                values = accumulated.setdefault(requirement_id, [0.0, 0.0])
                values[0] += float(shift_hours)
                if outside_flag:
                    values[1] += float(shift_hours)
            full_shift_totals = {
                requirement_id: (round(values[0], 2), round(values[1], 2))
                for requirement_id, values in accumulated.items()
            }

        diagnostics: list[PlanningSegmentCapacityDiagnosticReadModel] = []
        for requirement, resource in requirements:
            segment_id = _text(requirement.legacy_segment_id) or requirement.id
            allocated, outside = full_shift_totals.get(requirement.id, (0.0, 0.0))
            planned = round(float(requirement.planned_hours), 2)
            unplaced = round(max(planned - allocated, 0.0), 2)
            diagnostics.append(
                PlanningSegmentCapacityDiagnosticReadModel(
                    segment_id=segment_id,
                    resource_id=resource.id if resource is not None else None,
                    resource_name=resource.name if resource is not None else None,
                    planned_hours=planned,
                    allocated_hours=allocated,
                    outside_standard_hours=outside,
                    unplaced_hours=unplaced,
                    requires_outside_standard_hours=unplaced > 0.01,
                )
            )

        return PlanningCapacityGridReadModel(
            start=start,
            end=end,
            resources=tuple(resource_rows),
            segment_diagnostics=tuple(diagnostics),
        )

    def list_planning_actions(
        self,
        *,
        start: date,
        end: date,
    ) -> tuple[PlanningActionReadModel, ...]:
        """Return the coordinator inbox that historically sat above NiceGUI planning."""

        if end < start:
            start, end = end, start
        demands = {row.number: row for row in self.list_demands()}
        result: list[PlanningActionReadModel] = []

        for pending in self.list_pending_loads(start=start, end=end):
            demand = demands.get(pending.demand_number)
            if demand is None:
                continue
            competency_id = (
                demand.required_competency_ids[0]
                if len(demand.required_competency_ids) == 1
                else None
            )
            result.append(
                PlanningActionReadModel(
                    kind="APPROVAL",
                    reference=demand.number,
                    demand_number=demand.number,
                    segment_id=None,
                    project_number=demand.project_number,
                    project_name=demand.project_name,
                    task_code=demand.task_code,
                    task_label=demand.task_label,
                    start_date=pending.start_date,
                    end_date=pending.end_date,
                    planned_hours=float(
                        pending.projected_hours
                        if pending.projected_hours is not None
                        else pending.window_hours
                    ),
                    required_competency=demand.required_competencies,
                    required_competency_id=competency_id,
                    priority=demand.priority,
                    status=demand.status,
                    confirmation=demand.confirmation,
                    project_manager=demand.project_manager,
                    requester=demand.requester,
                    emergency_override_active=bool(demand.emergency_override_active),
                )
            )

        for segment in self.list_segments(
            start=start,
            end=end,
            include_cancelled=False,
        ):
            if segment.resource_name:
                continue
            if _normalized_text(segment.status) in {"annule", "termine"}:
                continue
            demand = demands.get(segment.demand_number or "")
            if demand is not None and not (
                demand.status == "En planification" or demand.emergency_override_active
            ):
                # A submitted modification keeps the old plan visible, but should not
                # invite assigning that stale plan until it is approved again.
                continue
            if segment.start_date is None or segment.end_date is None:
                continue
            result.append(
                PlanningActionReadModel(
                    kind="ASSIGNMENT",
                    reference=segment.segment_id,
                    demand_number=segment.demand_number,
                    segment_id=segment.segment_id,
                    project_number=segment.project_number,
                    project_name=segment.project_name,
                    task_code=demand.task_code if demand is not None else None,
                    task_label=demand.task_label if demand is not None else None,
                    start_date=segment.start_date,
                    end_date=segment.end_date,
                    planned_hours=float(segment.planned_hours),
                    required_competency=segment.required_competency,
                    required_competency_id=segment.required_competency_id,
                    priority=segment.priority,
                    status=segment.status,
                    confirmation=segment.confirmation,
                    project_manager=segment.project_manager,
                    requester=segment.requester,
                    emergency_override_active=(
                        bool(demand.emergency_override_active)
                        if demand is not None
                        else False
                    ),
                )
            )

        kind_order = {"APPROVAL": 0, "ASSIGNMENT": 1}
        return tuple(
            sorted(
                result,
                key=lambda row: (
                    row.start_date,
                    kind_order.get(row.kind, 9),
                    _text(row.project_number),
                    row.reference,
                ),
            )
        )

    def recommend_resources(
        self,
        segment_id: str,
    ) -> tuple[ResourceRecommendationReadModel, ...]:
        """Rank schedulable resources using the V1.6 competency/capacity semantics."""

        segment = self.get_segment(segment_id)
        if segment is None or segment.start_date is None or segment.end_date is None:
            return ()
        start = segment.start_date
        end = segment.end_date
        if end < start:
            start, end = end, start

        resources = self.list_schedulable_resources(start=start, end=end)
        if not resources:
            return ()
        rules = self._session.scalars(
            select(ResourceAvailabilityRule).where(ResourceAvailabilityRule.active.is_(True))
        ).all()
        availability = tuple(_availability_record(rule) for rule in rules)
        shifts = self.list_shifts(start=start, end=end)

        catalog_row = (
            self._session.get(Competency, segment.required_competency_id)
            if segment.required_competency_id
            else None
        )
        required_names = list(_split_competencies(segment.required_competency))
        if not required_names and catalog_row is not None:
            required_names.append(catalog_row.name)
        required_keys = {_normalized_text(name) for name in required_names if _text(name)}
        class_hints = {
            hint
            for hint in (
                *(_resource_class_hint(name) for name in required_names),
                _resource_class_hint(catalog_row.description) if catalog_row is not None else None,
            )
            if hint
        }
        required_class = next(iter(class_hints)) if len(class_hints) == 1 else None
        required_hours = max(float(segment.planned_hours), 0.0)
        candidates: list[dict[str, object]] = []

        for resource in resources:
            capacity = 0.0
            cursor = start
            while cursor <= end:
                capacity += availability_hours_for_day(availability, resource.id, cursor)
                cursor += timedelta(days=1)

            confirmed = 0.0
            tentative = 0.0
            outside = 0.0
            for shift in shifts:
                if shift.resource_id != resource.id or shift.segment_id == segment.segment_id:
                    continue
                shift_hours = float(shift.hours)
                if shift.outside_standard_hours:
                    outside += shift_hours
                elif shift.load_kind == "FIRM":
                    confirmed += shift_hours
                else:
                    tentative += shift_hours

            free_after_confirmed = max(capacity - confirmed, 0.0)
            prudent_free = max(capacity - confirmed - tentative, 0.0)
            overtime_needed = max(required_hours - prudent_free, 0.0)
            resource_skill_keys = {
                _normalized_text(name)
                for name in _split_competencies(resource.competencies)
            }
            if required_keys:
                competency_match = required_keys.issubset(resource_skill_keys)
            elif segment.required_competency_id:
                competency_match = segment.required_competency_id in resource.competency_ids
            else:
                competency_match = True
            class_match = (
                required_class is None
                or _normalized_text(resource.resource_class) == _normalized_text(required_class)
            )
            enough_prudent = prudent_free + 0.01 >= required_hours
            enough_after_confirmed = free_after_confirmed + 0.01 >= required_hours

            score = 0.0
            if competency_match:
                score += 20000.0
            if class_match:
                score += 10000.0
            if enough_prudent:
                score += 5000.0
            elif enough_after_confirmed:
                score += 2500.0
            score += min(prudent_free, required_hours) * 10.0
            score -= tentative * 2.0
            score -= overtime_needed * 8.0

            candidates.append(
                {
                    "resource": resource,
                    "competency_match": competency_match,
                    "class_match": class_match,
                    "capacity": round(capacity, 2),
                    "confirmed": round(confirmed, 2),
                    "tentative": round(tentative, 2),
                    "outside": round(outside, 2),
                    "free_after_confirmed": round(free_after_confirmed, 2),
                    "prudent_free": round(prudent_free, 2),
                    "overtime_needed": round(overtime_needed, 2),
                    "enough_after_confirmed": enough_after_confirmed,
                    "enough_prudent": enough_prudent,
                    "score": round(score, 2),
                }
            )

        candidates.sort(
            key=lambda row: (
                -int(bool(row["competency_match"])),
                -int(bool(row["class_match"])),
                -int(bool(row["enough_prudent"])),
                -float(row["score"]),
                -float(row["prudent_free"]),
                str(row["resource"].name).casefold(),
            )
        )

        result: list[ResourceRecommendationReadModel] = []
        for index, row in enumerate(candidates, start=1):
            resource = row["resource"]
            recommended = (
                index == 1
                and bool(row["competency_match"])
                and bool(row["class_match"])
            )
            result.append(
                ResourceRecommendationReadModel(
                    resource_id=resource.id,
                    resource_name=resource.name,
                    resource_class=resource.resource_class,
                    required_competency=(
                        "; ".join(required_names)
                        if required_names
                        else segment.required_competency
                    ),
                    required_class=required_class,
                    competency_match=bool(row["competency_match"]),
                    class_match=bool(row["class_match"]),
                    capacity_hours=float(row["capacity"]),
                    confirmed_hours=float(row["confirmed"]),
                    tentative_hours=float(row["tentative"]),
                    outside_standard_hours=float(row["outside"]),
                    free_after_confirmed=float(row["free_after_confirmed"]),
                    prudent_free=float(row["prudent_free"]),
                    overtime_needed=float(row["overtime_needed"]),
                    enough_after_confirmed=bool(row["enough_after_confirmed"]),
                    enough_prudent=bool(row["enough_prudent"]),
                    score=float(row["score"]),
                    rank=index,
                    recommended=recommended,
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
