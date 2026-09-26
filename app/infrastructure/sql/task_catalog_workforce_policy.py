from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...application.errors import ApplicationValidationError
from ...application.resource_classes import (
    RESOLUTION_CLASS,
    ResourceClassConfigurationService,
)
from ...application.task_catalog import (
    TaskCatalogWorkforcePolicyPort,
    TaskCatalogWorkforceProjection,
)
from .models import Project
from .resource_class_repository import SqlResourceClassRepository


def _text(value: object) -> str:
    return str(value or "").strip()


class SqlTaskCatalogWorkforcePolicy(TaskCatalogWorkforcePolicyPort):
    """Bridge targeted task sync to the canonical #454 class/cost rules."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._repository = SqlResourceClassRepository(session)
        self._service = ResourceClassConfigurationService(self._repository)

    def _project_id(self, project_number: str) -> str:
        normalized = _text(project_number)
        project_id = self._session.scalar(
            select(Project.id).where(Project.number == normalized)
        )
        if project_id is None:
            raise ApplicationValidationError(
                "Le projet ciblé doit exister localement avant la synchronisation des tâches.",
                code="task_catalog_project_not_found",
                context={"project_number": normalized},
            )
        return str(project_id)

    def project_task_projection(
        self,
        *,
        project_number: str,
        task_code: str,
        budget_amount_cad: Decimal | None,
    ) -> TaskCatalogWorkforceProjection:
        project_id = self._project_id(project_number)
        resolution = self._service.resolve(project_id, task_code)

        if resolution.status != RESOLUTION_CLASS or not resolution.resource_class_code:
            return TaskCatalogWorkforceProjection(
                eligible=False,
                resource_class_code=None,
                average_hourly_cost_cad=None,
                budget_hours=None,
                diagnostics=resolution.diagnostics,
            )

        if budget_amount_cad is None:
            resource_class = self._repository.get_resource_class(
                resolution.resource_class_code
            )
            cost = (
                resource_class.average_hourly_cost_cad
                if resource_class is not None
                else None
            )
            diagnostics = [*resolution.diagnostics, "budget_amount_missing"]
            if cost is None:
                diagnostics.append("resource_class_cost_missing")
            elif cost == 0:
                diagnostics.append("resource_class_cost_zero")
            elif cost < 0:
                diagnostics.append("resource_class_cost_negative")
            return TaskCatalogWorkforceProjection(
                eligible=True,
                resource_class_code=resolution.resource_class_code,
                average_hourly_cost_cad=cost,
                budget_hours=None,
                diagnostics=tuple(dict.fromkeys(diagnostics)),
            )

        projection = self._service.project_budget_hours(
            project_id,
            task_code,
            budget_amount_cad,
        )
        return TaskCatalogWorkforceProjection(
            eligible=bool(
                projection.resolution_status == RESOLUTION_CLASS
                and projection.resource_class_code
            ),
            resource_class_code=projection.resource_class_code,
            average_hourly_cost_cad=projection.average_hourly_cost_cad,
            budget_hours=projection.budget_hours,
            diagnostics=projection.diagnostics,
        )
