from __future__ import annotations

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from ...application.query_models import ResourceReadModel
from ...application.user_view_context import UserViewContextRepositoryPort
from .models import (
    Project,
    Resource,
    ResourceCompetency,
    ResourceRequirement,
    Shift,
)


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


class SqlUserViewContextRepository(UserViewContextRepositoryPort):
    """Resolve stable user/resource/project relationships without display-name joins."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_resource_by_external_id(
        self,
        employee_external_id: str,
    ) -> ResourceReadModel | None:
        external_id = str(employee_external_id or "").strip()
        if not external_id:
            return None
        resource = self._session.scalar(
            select(Resource).where(Resource.external_id == external_id)
        )
        if resource is None:
            return None
        competency_ids = tuple(
            self._session.scalars(
                select(ResourceCompetency.competency_id)
                .where(ResourceCompetency.resource_id == resource.id)
                .order_by(ResourceCompetency.competency_id)
            ).all()
        )
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

    def list_managed_project_ids(
        self,
        employee_external_id: str,
    ) -> tuple[str, ...]:
        external_id = str(employee_external_id or "").strip()
        if not external_id:
            return ()
        return tuple(
            self._session.scalars(
                select(Project.id)
                .where(Project.project_manager_external_id == external_id)
                .order_by(Project.number, Project.id)
            ).all()
        )

    def list_participating_project_ids(
        self,
        resource_id: str,
    ) -> tuple[str, ...]:
        wanted_resource_id = str(resource_id or "").strip()
        if not wanted_resource_id:
            return ()

        assigned = exists(
            select(1)
            .select_from(ResourceRequirement)
            .where(
                ResourceRequirement.project_id == Project.id,
                ResourceRequirement.assigned_resource_id == wanted_resource_id,
            )
        )
        shifted = exists(
            select(1)
            .select_from(Shift)
            .join(
                ResourceRequirement,
                Shift.resource_requirement_id == ResourceRequirement.id,
            )
            .where(
                ResourceRequirement.project_id == Project.id,
                Shift.resource_id == wanted_resource_id,
            )
        )
        return tuple(
            self._session.scalars(
                select(Project.id)
                .where(or_(assigned, shifted))
                .order_by(Project.number, Project.id)
            ).all()
        )
