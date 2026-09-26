from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from .errors import (
    ApplicationConflictError,
    ApplicationNotFoundError,
    ApplicationValidationError,
    call_application_port,
)


RESOLUTION_CLASS = "CLASS"
RESOLUTION_EXCLUDED = "EXCLUDED"
RESOLUTION_UNCLASSIFIED = "UNCLASSIFIED"
SOURCE_PROJECT_OVERRIDE = "PROJECT_OVERRIDE"
SOURCE_STANDARD = "STANDARD"


def _required_text(value: object, *, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ApplicationValidationError(
            f"{field} est requis.",
            code="resource_class_required_value",
            context={"field": field},
        )
    return normalized


def _decimal(value: Decimal | int | str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception as exc:
        raise ApplicationValidationError(
            "Le coût horaire moyen doit être un nombre décimal valide.",
            code="resource_class_cost_invalid",
            context={"value": str(value)},
        ) from exc


@dataclass(frozen=True, slots=True)
class ResourceClassConfigRecord:
    code: str
    label: str
    average_hourly_cost_cad: Decimal | None
    active: bool
    version: int


@dataclass(frozen=True, slots=True)
class TaskClassStandardRecord:
    task_code: str
    resource_class_code: str
    active: bool
    version: int


@dataclass(frozen=True, slots=True)
class ProjectTaskClassOverrideRecord:
    project_id: str
    task_code: str
    resource_class_code: str | None
    excluded: bool
    version: int


@dataclass(frozen=True, slots=True)
class TaskClassResolution:
    project_id: str
    task_code: str
    status: str
    resource_class_code: str | None
    configured_resource_class_code: str | None
    source: str | None
    diagnostics: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BudgetHoursProjection:
    project_id: str
    task_code: str
    budget_amount_cad: Decimal
    resource_class_code: str | None
    average_hourly_cost_cad: Decimal | None
    budget_hours: Decimal | None
    resolution_status: str
    diagnostics: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProjectTaskClassRule:
    task_code: str
    standard: TaskClassStandardRecord | None
    override: ProjectTaskClassOverrideRecord | None
    resolution: TaskClassResolution


class ResourceClassRepositoryPort(Protocol):
    def list_resource_classes(self) -> tuple[ResourceClassConfigRecord, ...]: ...
    def get_resource_class(self, code: str) -> ResourceClassConfigRecord | None: ...
    def create_resource_class(
        self,
        *,
        code: str,
        label: str,
        average_hourly_cost_cad: Decimal | None,
        active: bool,
    ) -> ResourceClassConfigRecord: ...
    def update_resource_class(
        self,
        code: str,
        *,
        expected_version: int,
        label: str | None,
        average_hourly_cost_cad: Decimal | None,
        average_hourly_cost_supplied: bool,
        active: bool | None,
    ) -> ResourceClassConfigRecord: ...

    def list_task_standards(self) -> tuple[TaskClassStandardRecord, ...]: ...
    def get_task_standard(self, task_code: str) -> TaskClassStandardRecord | None: ...
    def create_task_standard(
        self,
        *,
        task_code: str,
        resource_class_code: str,
        active: bool,
    ) -> TaskClassStandardRecord: ...
    def update_task_standard(
        self,
        task_code: str,
        *,
        expected_version: int,
        resource_class_code: str | None,
        active: bool | None,
    ) -> TaskClassStandardRecord: ...

    def project_exists(self, project_id: str) -> bool: ...
    def list_project_overrides(
        self,
        project_id: str,
    ) -> tuple[ProjectTaskClassOverrideRecord, ...]: ...
    def get_project_override(
        self,
        project_id: str,
        task_code: str,
    ) -> ProjectTaskClassOverrideRecord | None: ...
    def create_project_override(
        self,
        *,
        project_id: str,
        task_code: str,
        resource_class_code: str | None,
        excluded: bool,
    ) -> ProjectTaskClassOverrideRecord: ...
    def update_project_override(
        self,
        project_id: str,
        task_code: str,
        *,
        expected_version: int,
        resource_class_code: str | None,
        excluded: bool,
    ) -> ProjectTaskClassOverrideRecord: ...
    def delete_project_override(
        self,
        project_id: str,
        task_code: str,
        *,
        expected_version: int,
    ) -> None: ...


class ResourceClassConfigurationService:
    """Canonical workforce-class configuration and budget projection boundary.

    Resource classes describe the technical workforce need. They are intentionally
    independent from ApprovalScope, which describes approval authority.
    """

    def __init__(self, repository: ResourceClassRepositoryPort) -> None:
        self._repository = repository

    def list_resource_classes(self) -> tuple[ResourceClassConfigRecord, ...]:
        return tuple(
            call_application_port(
                self._repository.list_resource_classes,
                code_prefix="resource_class_read",
            )
        )

    def create_resource_class(
        self,
        *,
        code: str,
        label: str,
        average_hourly_cost_cad: Decimal | int | str | None,
        active: bool = True,
    ) -> ResourceClassConfigRecord:
        normalized_code = _required_text(code, field="code")
        normalized_label = _required_text(label, field="label")
        cost = _decimal(average_hourly_cost_cad)
        self._validate_usable_cost(cost, active=bool(active))

        existing = next(
            (
                row
                for row in self.list_resource_classes()
                if row.code.casefold() == normalized_code.casefold()
            ),
            None,
        )
        if existing is not None:
            raise ApplicationConflictError(
                f"La classe {normalized_code} existe déjà.",
                code="resource_class_code_conflict",
                context={"code": normalized_code},
            )
        return call_application_port(
            lambda: self._repository.create_resource_class(
                code=normalized_code,
                label=normalized_label,
                average_hourly_cost_cad=cost,
                active=bool(active),
            ),
            code_prefix="resource_class_create",
            context={"code": normalized_code},
        )

    def update_resource_class(
        self,
        code: str,
        *,
        expected_version: int,
        label: str | None = None,
        average_hourly_cost_cad: Decimal | int | str | None = None,
        average_hourly_cost_supplied: bool = False,
        active: bool | None = None,
    ) -> ResourceClassConfigRecord:
        normalized_code = _required_text(code, field="code")
        current = self._resource_class_or_not_found(normalized_code)
        next_label = current.label if label is None else _required_text(label, field="label")
        next_cost = (
            current.average_hourly_cost_cad
            if not average_hourly_cost_supplied
            else _decimal(average_hourly_cost_cad)
        )
        next_active = current.active if active is None else bool(active)
        self._validate_usable_cost(next_cost, active=next_active)
        return call_application_port(
            lambda: self._repository.update_resource_class(
                normalized_code,
                expected_version=int(expected_version),
                label=next_label,
                average_hourly_cost_cad=next_cost,
                average_hourly_cost_supplied=True,
                active=next_active,
            ),
            code_prefix="resource_class_update",
            context={"code": normalized_code},
        )

    def list_task_standards(self) -> tuple[TaskClassStandardRecord, ...]:
        return tuple(
            call_application_port(
                self._repository.list_task_standards,
                code_prefix="task_class_standard_read",
            )
        )

    def create_task_standard(
        self,
        *,
        task_code: str,
        resource_class_code: str,
        active: bool = True,
    ) -> TaskClassStandardRecord:
        normalized_task = _required_text(task_code, field="task_code")
        normalized_class = _required_text(
            resource_class_code,
            field="resource_class_code",
        )
        if self._repository.get_task_standard(normalized_task) is not None:
            raise ApplicationConflictError(
                f"Un standard existe déjà pour la tâche {normalized_task}.",
                code="task_class_standard_conflict",
                context={"task_code": normalized_task},
            )
        self._validate_mapping_class(normalized_class, require_active=bool(active))
        return call_application_port(
            lambda: self._repository.create_task_standard(
                task_code=normalized_task,
                resource_class_code=normalized_class,
                active=bool(active),
            ),
            code_prefix="task_class_standard_create",
            context={"task_code": normalized_task},
        )

    def update_task_standard(
        self,
        task_code: str,
        *,
        expected_version: int,
        resource_class_code: str | None = None,
        active: bool | None = None,
    ) -> TaskClassStandardRecord:
        normalized_task = _required_text(task_code, field="task_code")
        current = self._task_standard_or_not_found(normalized_task)
        next_class = (
            current.resource_class_code
            if resource_class_code is None
            else _required_text(resource_class_code, field="resource_class_code")
        )
        next_active = current.active if active is None else bool(active)
        self._validate_mapping_class(next_class, require_active=next_active)
        return call_application_port(
            lambda: self._repository.update_task_standard(
                normalized_task,
                expected_version=int(expected_version),
                resource_class_code=next_class,
                active=next_active,
            ),
            code_prefix="task_class_standard_update",
            context={"task_code": normalized_task},
        )

    def list_project_task_rules(
        self,
        project_id: str,
    ) -> tuple[ProjectTaskClassRule, ...]:
        normalized_project = self._project_or_not_found(project_id)
        standards = {row.task_code: row for row in self.list_task_standards()}
        overrides = {
            row.task_code: row
            for row in call_application_port(
                lambda: self._repository.list_project_overrides(normalized_project),
                code_prefix="project_task_class_override_read",
                context={"project_id": normalized_project},
            )
        }
        task_codes = sorted(set(standards) | set(overrides))
        return tuple(
            ProjectTaskClassRule(
                task_code=task_code,
                standard=standards.get(task_code),
                override=overrides.get(task_code),
                resolution=self.resolve(normalized_project, task_code),
            )
            for task_code in task_codes
        )

    def set_project_override(
        self,
        project_id: str,
        task_code: str,
        *,
        resource_class_code: str | None = None,
        excluded: bool = False,
        expected_version: int | None = None,
    ) -> ProjectTaskClassOverrideRecord:
        normalized_project = self._project_or_not_found(project_id)
        normalized_task = _required_text(task_code, field="task_code")
        normalized_class = (
            None
            if excluded
            else _required_text(
                resource_class_code,
                field="resource_class_code",
            )
        )
        if not excluded:
            assert normalized_class is not None
            self._validate_mapping_class(normalized_class, require_active=True)

        current = call_application_port(
            lambda: self._repository.get_project_override(
                normalized_project,
                normalized_task,
            ),
            code_prefix="project_task_class_override_read",
            context={
                "project_id": normalized_project,
                "task_code": normalized_task,
            },
        )
        if current is None:
            if expected_version is not None:
                raise ApplicationConflictError(
                    "L'exception projet n'existe plus.",
                    code="project_task_class_override_version_conflict",
                    context={
                        "project_id": normalized_project,
                        "task_code": normalized_task,
                    },
                )
            return call_application_port(
                lambda: self._repository.create_project_override(
                    project_id=normalized_project,
                    task_code=normalized_task,
                    resource_class_code=normalized_class,
                    excluded=bool(excluded),
                ),
                code_prefix="project_task_class_override_create",
                context={
                    "project_id": normalized_project,
                    "task_code": normalized_task,
                },
            )
        if expected_version is None:
            raise ApplicationValidationError(
                "La version attendue de l'exception projet est requise.",
                code="project_task_class_override_version_required",
                context={
                    "project_id": normalized_project,
                    "task_code": normalized_task,
                },
            )
        return call_application_port(
            lambda: self._repository.update_project_override(
                normalized_project,
                normalized_task,
                expected_version=int(expected_version),
                resource_class_code=normalized_class,
                excluded=bool(excluded),
            ),
            code_prefix="project_task_class_override_update",
            context={
                "project_id": normalized_project,
                "task_code": normalized_task,
            },
        )

    def remove_project_override(
        self,
        project_id: str,
        task_code: str,
        *,
        expected_version: int,
    ) -> TaskClassResolution:
        normalized_project = self._project_or_not_found(project_id)
        normalized_task = _required_text(task_code, field="task_code")
        current = call_application_port(
            lambda: self._repository.get_project_override(
                normalized_project,
                normalized_task,
            ),
            code_prefix="project_task_class_override_read",
            context={
                "project_id": normalized_project,
                "task_code": normalized_task,
            },
        )
        if current is None:
            raise ApplicationNotFoundError(
                "L'exception projet est introuvable.",
                code="project_task_class_override_not_found",
                context={
                    "project_id": normalized_project,
                    "task_code": normalized_task,
                },
            )
        call_application_port(
            lambda: self._repository.delete_project_override(
                normalized_project,
                normalized_task,
                expected_version=int(expected_version),
            ),
            code_prefix="project_task_class_override_delete",
            context={
                "project_id": normalized_project,
                "task_code": normalized_task,
            },
        )
        return self.resolve(normalized_project, normalized_task)

    def resolve(
        self,
        project_id: str,
        task_code: str,
    ) -> TaskClassResolution:
        normalized_project = _required_text(project_id, field="project_id")
        normalized_task = _required_text(task_code, field="task_code")
        override = call_application_port(
            lambda: self._repository.get_project_override(
                normalized_project,
                normalized_task,
            ),
            code_prefix="project_task_class_override_read",
            context={
                "project_id": normalized_project,
                "task_code": normalized_task,
            },
        )
        if override is not None:
            if override.excluded:
                return TaskClassResolution(
                    project_id=normalized_project,
                    task_code=normalized_task,
                    status=RESOLUTION_EXCLUDED,
                    resource_class_code=None,
                    configured_resource_class_code=None,
                    source=SOURCE_PROJECT_OVERRIDE,
                    diagnostics=("task_excluded",),
                )
            return self._resolve_class_reference(
                project_id=normalized_project,
                task_code=normalized_task,
                resource_class_code=override.resource_class_code,
                source=SOURCE_PROJECT_OVERRIDE,
                missing_diagnostic="override_resource_class_missing",
                inactive_diagnostic="override_resource_class_inactive",
            )

        standard = call_application_port(
            lambda: self._repository.get_task_standard(normalized_task),
            code_prefix="task_class_standard_read",
            context={"task_code": normalized_task},
        )
        if standard is None:
            return TaskClassResolution(
                project_id=normalized_project,
                task_code=normalized_task,
                status=RESOLUTION_UNCLASSIFIED,
                resource_class_code=None,
                configured_resource_class_code=None,
                source=None,
                diagnostics=("task_standard_missing",),
            )
        if not standard.active:
            return TaskClassResolution(
                project_id=normalized_project,
                task_code=normalized_task,
                status=RESOLUTION_UNCLASSIFIED,
                resource_class_code=None,
                configured_resource_class_code=standard.resource_class_code,
                source=SOURCE_STANDARD,
                diagnostics=("task_standard_inactive",),
            )
        return self._resolve_class_reference(
            project_id=normalized_project,
            task_code=normalized_task,
            resource_class_code=standard.resource_class_code,
            source=SOURCE_STANDARD,
            missing_diagnostic="standard_resource_class_missing",
            inactive_diagnostic="standard_resource_class_inactive",
        )

    def project_budget_hours(
        self,
        project_id: str,
        task_code: str,
        budget_amount_cad: Decimal | int | str,
    ) -> BudgetHoursProjection:
        resolution = self.resolve(project_id, task_code)
        try:
            budget = Decimal(str(budget_amount_cad))
        except Exception as exc:
            raise ApplicationValidationError(
                "BudgetAmount doit être un montant décimal valide.",
                code="budget_amount_invalid",
                context={"value": str(budget_amount_cad)},
            ) from exc

        diagnostics = list(resolution.diagnostics)
        if budget == 0:
            diagnostics.append("budget_amount_zero")
        elif budget < 0:
            diagnostics.append("budget_amount_negative")

        if resolution.status != RESOLUTION_CLASS or not resolution.resource_class_code:
            return BudgetHoursProjection(
                project_id=resolution.project_id,
                task_code=resolution.task_code,
                budget_amount_cad=budget,
                resource_class_code=None,
                average_hourly_cost_cad=None,
                budget_hours=None,
                resolution_status=resolution.status,
                diagnostics=tuple(dict.fromkeys(diagnostics)),
            )

        resource_class = call_application_port(
            lambda: self._repository.get_resource_class(
                resolution.resource_class_code or ""
            ),
            code_prefix="resource_class_read",
            context={"code": resolution.resource_class_code},
        )
        cost = (
            resource_class.average_hourly_cost_cad
            if resource_class is not None
            else None
        )
        hours: Decimal | None = None
        if cost is None:
            diagnostics.append("resource_class_cost_missing")
        elif cost == 0:
            diagnostics.append("resource_class_cost_zero")
        elif cost < 0:
            diagnostics.append("resource_class_cost_negative")
        else:
            hours = budget / cost

        return BudgetHoursProjection(
            project_id=resolution.project_id,
            task_code=resolution.task_code,
            budget_amount_cad=budget,
            resource_class_code=resolution.resource_class_code,
            average_hourly_cost_cad=cost,
            budget_hours=hours,
            resolution_status=resolution.status,
            diagnostics=tuple(dict.fromkeys(diagnostics)),
        )

    @staticmethod
    def _validate_usable_cost(
        cost: Decimal | None,
        *,
        active: bool,
    ) -> None:
        if active and (cost is None or cost <= 0):
            raise ApplicationValidationError(
                "Une classe active doit avoir un coût horaire moyen supérieur à 0.",
                code="resource_class_active_cost_required",
                context={
                    "average_hourly_cost_cad": (
                        None if cost is None else str(cost)
                    )
                },
            )

    def _validate_mapping_class(
        self,
        resource_class_code: str,
        *,
        require_active: bool,
    ) -> ResourceClassConfigRecord:
        row = self._resource_class_or_not_found(resource_class_code)
        if require_active and not row.active:
            raise ApplicationValidationError(
                f"La classe {row.code} est inactive.",
                code="resource_class_inactive",
                context={"code": row.code},
            )
        return row

    def _resource_class_or_not_found(
        self,
        code: str,
    ) -> ResourceClassConfigRecord:
        normalized = _required_text(code, field="resource_class_code")
        row = call_application_port(
            lambda: self._repository.get_resource_class(normalized),
            code_prefix="resource_class_read",
            context={"code": normalized},
        )
        if row is None:
            raise ApplicationNotFoundError(
                f"Classe {normalized} introuvable.",
                code="resource_class_not_found",
                context={"code": normalized},
            )
        return row

    def _task_standard_or_not_found(
        self,
        task_code: str,
    ) -> TaskClassStandardRecord:
        row = call_application_port(
            lambda: self._repository.get_task_standard(task_code),
            code_prefix="task_class_standard_read",
            context={"task_code": task_code},
        )
        if row is None:
            raise ApplicationNotFoundError(
                f"Standard de tâche {task_code} introuvable.",
                code="task_class_standard_not_found",
                context={"task_code": task_code},
            )
        return row

    def _project_or_not_found(self, project_id: str) -> str:
        normalized = _required_text(project_id, field="project_id")
        exists = call_application_port(
            lambda: self._repository.project_exists(normalized),
            code_prefix="project_read",
            context={"project_id": normalized},
        )
        if not exists:
            raise ApplicationNotFoundError(
                f"Projet {normalized} introuvable.",
                code="project_not_found",
                context={"project_id": normalized},
            )
        return normalized

    def _resolve_class_reference(
        self,
        *,
        project_id: str,
        task_code: str,
        resource_class_code: str | None,
        source: str,
        missing_diagnostic: str,
        inactive_diagnostic: str,
    ) -> TaskClassResolution:
        configured = str(resource_class_code or "").strip() or None
        if configured is None:
            return TaskClassResolution(
                project_id=project_id,
                task_code=task_code,
                status=RESOLUTION_UNCLASSIFIED,
                resource_class_code=None,
                configured_resource_class_code=None,
                source=source,
                diagnostics=(missing_diagnostic,),
            )
        row = call_application_port(
            lambda: self._repository.get_resource_class(configured),
            code_prefix="resource_class_read",
            context={"code": configured},
        )
        if row is None:
            return TaskClassResolution(
                project_id=project_id,
                task_code=task_code,
                status=RESOLUTION_UNCLASSIFIED,
                resource_class_code=None,
                configured_resource_class_code=configured,
                source=source,
                diagnostics=(missing_diagnostic,),
            )
        if not row.active:
            return TaskClassResolution(
                project_id=project_id,
                task_code=task_code,
                status=RESOLUTION_UNCLASSIFIED,
                resource_class_code=None,
                configured_resource_class_code=configured,
                source=source,
                diagnostics=(inactive_diagnostic,),
            )
        return TaskClassResolution(
            project_id=project_id,
            task_code=task_code,
            status=RESOLUTION_CLASS,
            resource_class_code=row.code,
            configured_resource_class_code=row.code,
            source=source,
            diagnostics=(),
        )
