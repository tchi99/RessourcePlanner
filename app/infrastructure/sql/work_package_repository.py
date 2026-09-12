from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...application.errors import ApplicationConflictError
from ...application.query_models import WorkPackageReadModel
from ...application.repository_ports import WorkPackageRepositoryPort
from .models import Project, WorkforceRequest, WorkPackage


def _text(value: object) -> str:
    return str(value or "").strip()


def _optional_text(value: object) -> str | None:
    normalized = _text(value)
    return normalized or None


def _decimal(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    return Decimal(str(value).replace(",", "."))


class SqlWorkPackageRepository(WorkPackageRepositoryPort):
    """SQLAlchemy WorkPackage mutations inside the caller-owned transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _read_model(work_package: WorkPackage, project: Project) -> WorkPackageReadModel:
        return WorkPackageReadModel(
            id=work_package.id,
            reference=_optional_text(work_package.legacy_effort_id) or work_package.id,
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
            status=_text(work_package.status) or "planned",
        )

    def _row(self, reference: str) -> tuple[WorkPackage, Project] | None:
        wanted = _text(reference)
        if not wanted:
            return None
        return self._session.execute(
            select(WorkPackage, Project)
            .join(Project, WorkPackage.project_id == Project.id)
            .where(
                (WorkPackage.id == wanted)
                | (WorkPackage.legacy_effort_id == wanted)
            )
        ).one_or_none()

    def get(self, reference: str) -> WorkPackageReadModel | None:
        row = self._row(reference)
        if row is None:
            return None
        work_package, project = row
        return self._read_model(work_package, project)

    def _entity(self, reference: str) -> WorkPackage:
        wanted = _text(reference)
        work_package = self._session.scalar(
            select(WorkPackage).where(
                (WorkPackage.id == wanted)
                | (WorkPackage.legacy_effort_id == wanted)
            )
        )
        if work_package is None:
            raise KeyError(f"WorkPackage {wanted} introuvable")
        return work_package

    def _project(self, number: object) -> Project:
        project_number = _text(number)
        project = self._session.scalar(
            select(Project).where(Project.number == project_number)
        )
        if project is None:
            raise KeyError(f"Projet {project_number} introuvable")
        return project

    def create(self, values: Mapping[str, Any]) -> str:
        project = self._project(values.get("project_number"))
        work_package = WorkPackage(
            project_id=project.id,
            code=_optional_text(values.get("code")),
            name=_text(values.get("name")),
            description=_optional_text(values.get("description")),
            start_date=values.get("start_date"),
            end_date=values.get("end_date"),
            planned_hours=_decimal(values.get("planned_hours")),
            status=_text(values.get("status")) or "planned",
        )
        self._session.add(work_package)
        self._session.flush()
        return work_package.id

    def update(self, reference: str, updates: Mapping[str, Any]) -> str:
        work_package = self._entity(reference)

        if "project_number" in updates:
            project = self._project(updates.get("project_number"))
            if project.id != work_package.project_id:
                linked_requests = self._session.scalar(
                    select(func.count())
                    .select_from(WorkforceRequest)
                    .where(WorkforceRequest.work_package_id == work_package.id)
                ) or 0
                if linked_requests:
                    raise ApplicationConflictError(
                        "Le projet d'un WorkPackage lié à des demandes ne peut pas être changé.",
                        code="work_package_project_change_linked_demands",
                        context={
                            "reference": _optional_text(work_package.legacy_effort_id) or work_package.id,
                            "linked_demands": int(linked_requests),
                        },
                    )
                work_package.project_id = project.id

        if "code" in updates:
            work_package.code = _optional_text(updates.get("code"))
        if "name" in updates:
            work_package.name = _text(updates.get("name"))
        if "description" in updates:
            work_package.description = _optional_text(updates.get("description"))
        if "start_date" in updates:
            work_package.start_date = updates.get("start_date")
        if "end_date" in updates:
            work_package.end_date = updates.get("end_date")
        if "planned_hours" in updates:
            work_package.planned_hours = _decimal(updates.get("planned_hours"))
        if "status" in updates:
            work_package.status = _text(updates.get("status"))

        self._session.flush()
        return _optional_text(work_package.legacy_effort_id) or work_package.id
