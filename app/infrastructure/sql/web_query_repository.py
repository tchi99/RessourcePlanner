from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...application import WorkPackageReadModel
from .models import Project, WorkPackage
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
    """SQL query surface extended with WorkPackage reads required by React V2.

    Keeping this projection inside infrastructure preserves the server boundary: route
    modules depend only on application query contracts and the composition root remains
    the only server module that selects concrete SQL adapters.
    """

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
