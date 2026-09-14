from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...application import ResourceAvailabilityRuleReadModel, WorkPackageReadModel
from .models import Project, Resource, ResourceAvailabilityRule, WorkPackage
from .query_repository import SqlPlannerQueryRepository


INACTIVE_WORK_PACKAGE_STATUSES = {
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
    normalized = _text(value)
    return normalized or None


class SqlPlannerQueryRepositoryWeb(SqlPlannerQueryRepository):
    """SQL query surface extended with reads required by React V2."""

    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self._web_session = session

    def list_work_packages(
        self,
        *,
        project_number: str | None = None,
        active_only: bool = True,
    ) -> tuple[WorkPackageReadModel, ...]:
        statement = (
            select(WorkPackage, Project)
            .join(Project, WorkPackage.project_id == Project.id)
            .order_by(Project.number, WorkPackage.start_date, WorkPackage.name, WorkPackage.id)
        )
        wanted_project = _text(project_number)
        if wanted_project:
            statement = statement.where(Project.number == wanted_project)

        rows = self._web_session.execute(statement).all()
        result: list[WorkPackageReadModel] = []
        for work_package, project in rows:
            status = _text(work_package.status) or "planned"
            if active_only and status.casefold() in INACTIVE_WORK_PACKAGE_STATUSES:
                continue
            reference = _optional_text(work_package.legacy_effort_id) or work_package.id
            result.append(
                WorkPackageReadModel(
                    id=work_package.id,
                    reference=reference,
                    project_number=project.number,
                    code=_optional_text(work_package.code),
                    name=work_package.name,
                    description=_optional_text(work_package.description),
                    start_date=work_package.start_date,
                    end_date=work_package.end_date,
                    planned_hours=(
                        float(work_package.planned_hours)
                        if work_package.planned_hours is not None
                        else None
                    ),
                    status=status,
                )
            )
        return tuple(result)

    def list_availability_rules(
        self,
        *,
        resource_id: str | None = None,
        include_global: bool = True,
        active_only: bool = True,
    ) -> tuple[ResourceAvailabilityRuleReadModel, ...]:
        statement = (
            select(ResourceAvailabilityRule, Resource)
            .outerjoin(Resource, ResourceAvailabilityRule.resource_id == Resource.id)
            .order_by(
                ResourceAvailabilityRule.start_date,
                ResourceAvailabilityRule.availability_type,
                ResourceAvailabilityRule.id,
            )
        )
        if active_only:
            statement = statement.where(ResourceAvailabilityRule.active.is_(True))

        wanted_resource = _text(resource_id)
        if wanted_resource:
            if include_global:
                statement = statement.where(
                    (ResourceAvailabilityRule.resource_id == wanted_resource)
                    | (ResourceAvailabilityRule.resource_id.is_(None))
                )
            else:
                statement = statement.where(
                    ResourceAvailabilityRule.resource_id == wanted_resource
                )
        elif not include_global:
            statement = statement.where(ResourceAvailabilityRule.resource_id.is_not(None))

        rows = self._web_session.execute(statement).all()
        return tuple(
            ResourceAvailabilityRuleReadModel(
                id=rule.id,
                availability_type=rule.availability_type,
                resource_id=rule.resource_id,
                resource_name=resource.name if resource is not None else None,
                start_date=rule.start_date,
                end_date=rule.end_date,
                weekdays=_optional_text(rule.weekdays),
                start_time=rule.start_time,
                end_time=rule.end_time,
                note=_optional_text(rule.note),
                active=bool(rule.active),
            )
            for rule, resource in rows
        )
