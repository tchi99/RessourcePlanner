from __future__ import annotations

from decimal import Decimal

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from ...application.errors import ApplicationConflictError
from ...application.resource_classes import (
    ProjectTaskClassOverrideRecord,
    ResourceClassConfigRecord,
    ResourceClassRepositoryPort,
    TaskClassStandardRecord,
)
from .models import Project
from .resource_class_models import (
    ProjectTaskClassOverride,
    ResourceClassConfig,
    TaskClassStandard,
)


def _text(value: object) -> str:
    return str(value or "").strip()


def _class_record(row: ResourceClassConfig) -> ResourceClassConfigRecord:
    return ResourceClassConfigRecord(
        code=row.code,
        label=row.label,
        average_hourly_cost_cad=(
            Decimal(row.average_hourly_cost_cad)
            if row.average_hourly_cost_cad is not None
            else None
        ),
        active=bool(row.active),
        version=int(row.version or 1),
    )


def _standard_record(row: TaskClassStandard) -> TaskClassStandardRecord:
    return TaskClassStandardRecord(
        task_code=row.task_code,
        resource_class_code=row.resource_class_code,
        active=bool(row.active),
        version=int(row.version or 1),
    )


def _override_record(
    row: ProjectTaskClassOverride,
) -> ProjectTaskClassOverrideRecord:
    return ProjectTaskClassOverrideRecord(
        project_id=row.project_id,
        task_code=row.task_code,
        resource_class_code=(
            _text(row.resource_class_code) or None
        ),
        excluded=bool(row.excluded),
        version=int(row.version or 1),
    )


class SqlResourceClassRepository(ResourceClassRepositoryPort):
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_resource_classes(self) -> tuple[ResourceClassConfigRecord, ...]:
        rows = self._session.scalars(
            select(ResourceClassConfig).order_by(
                ResourceClassConfig.code
            )
        ).all()
        return tuple(_class_record(row) for row in rows)

    def get_resource_class(
        self,
        code: str,
    ) -> ResourceClassConfigRecord | None:
        row = self._session.get(ResourceClassConfig, _text(code))
        return _class_record(row) if row is not None else None

    def create_resource_class(
        self,
        *,
        code: str,
        label: str,
        average_hourly_cost_cad: Decimal | None,
        active: bool,
    ) -> ResourceClassConfigRecord:
        row = ResourceClassConfig(
            code=_text(code),
            label=_text(label),
            average_hourly_cost_cad=average_hourly_cost_cad,
            active=bool(active),
            version=1,
        )
        self._session.add(row)
        self._session.flush()
        self._session.refresh(row)
        return _class_record(row)

    def update_resource_class(
        self,
        code: str,
        *,
        expected_version: int,
        label: str | None,
        average_hourly_cost_cad: Decimal | None,
        average_hourly_cost_supplied: bool,
        active: bool | None,
    ) -> ResourceClassConfigRecord:
        identifier = _text(code)
        values: dict[str, object] = {
            "version": int(expected_version) + 1,
        }
        if label is not None:
            values["label"] = _text(label)
        if average_hourly_cost_supplied:
            values["average_hourly_cost_cad"] = average_hourly_cost_cad
        if active is not None:
            values["active"] = bool(active)
        result = self._session.execute(
            update(ResourceClassConfig)
            .where(
                ResourceClassConfig.code == identifier,
                ResourceClassConfig.version == int(expected_version),
            )
            .values(**values)
        )
        if result.rowcount != 1:
            self._session.expire_all()
            raise ApplicationConflictError(
                "La classe a été modifiée depuis sa lecture.",
                code="resource_class_version_conflict",
                context={
                    "code": identifier,
                    "expected_version": int(expected_version),
                },
            )
        self._session.flush()
        self._session.expire_all()
        row = self._session.get(ResourceClassConfig, identifier)
        if row is None:
            raise KeyError(f"Classe {identifier} introuvable")
        return _class_record(row)

    def list_task_standards(self) -> tuple[TaskClassStandardRecord, ...]:
        rows = self._session.scalars(
            select(TaskClassStandard).order_by(
                TaskClassStandard.task_code
            )
        ).all()
        return tuple(_standard_record(row) for row in rows)

    def get_task_standard(
        self,
        task_code: str,
    ) -> TaskClassStandardRecord | None:
        row = self._session.get(TaskClassStandard, _text(task_code))
        return _standard_record(row) if row is not None else None

    def create_task_standard(
        self,
        *,
        task_code: str,
        resource_class_code: str,
        active: bool,
    ) -> TaskClassStandardRecord:
        row = TaskClassStandard(
            task_code=_text(task_code),
            resource_class_code=_text(resource_class_code),
            active=bool(active),
            version=1,
        )
        self._session.add(row)
        self._session.flush()
        return _standard_record(row)

    def update_task_standard(
        self,
        task_code: str,
        *,
        expected_version: int,
        resource_class_code: str | None,
        active: bool | None,
    ) -> TaskClassStandardRecord:
        identifier = _text(task_code)
        values: dict[str, object] = {
            "version": int(expected_version) + 1,
        }
        if resource_class_code is not None:
            values["resource_class_code"] = _text(resource_class_code)
        if active is not None:
            values["active"] = bool(active)
        result = self._session.execute(
            update(TaskClassStandard)
            .where(
                TaskClassStandard.task_code == identifier,
                TaskClassStandard.version == int(expected_version),
            )
            .values(**values)
        )
        if result.rowcount != 1:
            self._session.expire_all()
            raise ApplicationConflictError(
                "Le standard de tâche a été modifié depuis sa lecture.",
                code="task_class_standard_version_conflict",
                context={
                    "task_code": identifier,
                    "expected_version": int(expected_version),
                },
            )
        self._session.flush()
        self._session.expire_all()
        row = self._session.get(TaskClassStandard, identifier)
        if row is None:
            raise KeyError(f"Standard de tâche {identifier} introuvable")
        return _standard_record(row)

    def project_exists(self, project_id: str) -> bool:
        return self._session.get(Project, _text(project_id)) is not None

    def list_project_overrides(
        self,
        project_id: str,
    ) -> tuple[ProjectTaskClassOverrideRecord, ...]:
        rows = self._session.scalars(
            select(ProjectTaskClassOverride)
            .where(
                ProjectTaskClassOverride.project_id == _text(project_id)
            )
            .order_by(ProjectTaskClassOverride.task_code)
        ).all()
        return tuple(_override_record(row) for row in rows)

    def get_project_override(
        self,
        project_id: str,
        task_code: str,
    ) -> ProjectTaskClassOverrideRecord | None:
        row = self._session.get(
            ProjectTaskClassOverride,
            (_text(project_id), _text(task_code)),
        )
        return _override_record(row) if row is not None else None

    def create_project_override(
        self,
        *,
        project_id: str,
        task_code: str,
        resource_class_code: str | None,
        excluded: bool,
    ) -> ProjectTaskClassOverrideRecord:
        row = ProjectTaskClassOverride(
            project_id=_text(project_id),
            task_code=_text(task_code),
            resource_class_code=(
                None if excluded else (_text(resource_class_code) or None)
            ),
            excluded=bool(excluded),
            version=1,
        )
        self._session.add(row)
        self._session.flush()
        return _override_record(row)

    def update_project_override(
        self,
        project_id: str,
        task_code: str,
        *,
        expected_version: int,
        resource_class_code: str | None,
        excluded: bool,
    ) -> ProjectTaskClassOverrideRecord:
        normalized_project = _text(project_id)
        normalized_task = _text(task_code)
        result = self._session.execute(
            update(ProjectTaskClassOverride)
            .where(
                ProjectTaskClassOverride.project_id == normalized_project,
                ProjectTaskClassOverride.task_code == normalized_task,
                ProjectTaskClassOverride.version == int(expected_version),
            )
            .values(
                resource_class_code=(
                    None
                    if excluded
                    else (_text(resource_class_code) or None)
                ),
                excluded=bool(excluded),
                version=int(expected_version) + 1,
            )
        )
        if result.rowcount != 1:
            self._session.expire_all()
            raise ApplicationConflictError(
                "L'exception projet a été modifiée depuis sa lecture.",
                code="project_task_class_override_version_conflict",
                context={
                    "project_id": normalized_project,
                    "task_code": normalized_task,
                    "expected_version": int(expected_version),
                },
            )
        self._session.flush()
        self._session.expire_all()
        row = self._session.get(
            ProjectTaskClassOverride,
            (normalized_project, normalized_task),
        )
        if row is None:
            raise KeyError(
                f"Exception {normalized_project}/{normalized_task} introuvable"
            )
        return _override_record(row)

    def delete_project_override(
        self,
        project_id: str,
        task_code: str,
        *,
        expected_version: int,
    ) -> None:
        normalized_project = _text(project_id)
        normalized_task = _text(task_code)
        result = self._session.execute(
            delete(ProjectTaskClassOverride).where(
                ProjectTaskClassOverride.project_id == normalized_project,
                ProjectTaskClassOverride.task_code == normalized_task,
                ProjectTaskClassOverride.version == int(expected_version),
            )
        )
        if result.rowcount != 1:
            self._session.expire_all()
            raise ApplicationConflictError(
                "L'exception projet a été modifiée depuis sa lecture.",
                code="project_task_class_override_version_conflict",
                context={
                    "project_id": normalized_project,
                    "task_code": normalized_task,
                    "expected_version": int(expected_version),
                },
            )
        self._session.flush()
