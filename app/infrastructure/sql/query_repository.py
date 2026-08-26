from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...application.query_models import ProjectReadModel, ResourceReadModel, ShiftReadModel
from ...application.query_ports import PlannerQueryPort
from ...application.read_models import DemandReadModel, SegmentReadModel
from .demand_repository import SqlDemandRepository
from .models import Project, Resource, ResourceRequirement, Shift
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


class SqlPlannerQueryRepository(PlannerQueryPort):
    """Read-only SQL projection for the future web frontend."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._demands = SqlDemandRepository(session)
        self._segments = SqlSegmentRepository(session)

    def list_projects(self, *, active_only: bool = False) -> tuple[ProjectReadModel, ...]:
        rows = self._session.scalars(select(Project).order_by(Project.number)).all()
        result: list[ProjectReadModel] = []
        for project in rows:
            status = _text(project.status) or "active"
            if active_only and status.casefold() in INACTIVE_PROJECT_STATUSES:
                continue
            result.append(
                ProjectReadModel(
                    id=project.id,
                    number=project.number,
                    name=project.name,
                    client=_optional_text(project.client),
                    project_manager=_optional_text(project.project_manager_name),
                    status=status,
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
        return tuple(
            ResourceReadModel(
                id=resource.id,
                name=resource.name,
                resource_class=_optional_text(resource.resource_class),
                competencies=_optional_text(resource.competencies),
                note=_optional_text(resource.note),
                active=bool(resource.active),
                sort_order=int(resource.sort_order or 0),
                external_id=_optional_text(resource.external_id),
            )
            for resource in rows
        )

    def list_demands(self) -> tuple[DemandReadModel, ...]:
        return tuple(self._demands.list())

    def get_demand(self, number: str) -> DemandReadModel | None:
        return self._demands.get(number)

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
    ) -> tuple[ShiftReadModel, ...]:
        statement = (
            select(Shift, ResourceRequirement, Resource)
            .join(
                ResourceRequirement,
                Shift.resource_requirement_id == ResourceRequirement.id,
            )
            .join(Resource, Shift.resource_id == Resource.id)
        )
        if start is not None:
            statement = statement.where(Shift.work_date >= start)
        if end is not None:
            statement = statement.where(Shift.work_date <= end)
        wanted_resource = _text(resource_name)
        if wanted_resource:
            statement = statement.where(Resource.name == wanted_resource)

        rows = self._session.execute(
            statement.order_by(
                Shift.work_date,
                Resource.sort_order,
                Resource.name,
                Shift.locked.desc(),
                Shift.id,
            )
        ).all()
        return tuple(
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
                confirmation=_optional_text(shift.confirmation),
                note=_optional_text(shift.note),
            )
            for shift, requirement, resource in rows
        )
