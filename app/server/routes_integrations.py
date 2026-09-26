from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Callable

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..application import (
    EmployeeSourcePort,
    EmployeeSyncResult,
    EmployeeSyncService,
    ErpUserSourcePort,
    ErpUserSyncResult,
    ErpUserSyncService,
    ProjectSourcePort,
    ProjectSyncResult,
    ProjectSyncService,
)
from ..application.errors import ApplicationUnavailableError
from ..infrastructure.sql import (
    SqlEmployeeSyncRepository,
    SqlErpUserDirectoryRepository,
    SqlProjectSyncRepository,
)
from .performance import performance_phase, record_external_call, record_external_items


SessionProvider = Callable[[], Iterator[Session]]


class _InstrumentedEmployeeSource:
    def __init__(self, source: EmployeeSourcePort) -> None:
        self._source = source

    def list_employees(self):
        record_external_call()
        with performance_phase("external"):
            rows = tuple(self._source.list_employees())
        record_external_items(len(rows))
        return rows


class _InstrumentedErpUserSource:
    def __init__(self, source: ErpUserSourcePort) -> None:
        self._source = source

    def list_users(self):
        record_external_call()
        with performance_phase("external"):
            rows = tuple(self._source.list_users())
        record_external_items(len(rows))
        return rows


class _InstrumentedProjectSource:
    def __init__(self, source: ProjectSourcePort) -> None:
        self._source = source

    def list_projects(self):
        record_external_call()
        with performance_phase("external"):
            rows = tuple(self._source.list_projects())
        record_external_items(len(rows))
        return rows


def build_integration_router(
    session_dependency: SessionProvider,
    *,
    project_source: ProjectSourcePort | None = None,
    employee_source: EmployeeSourcePort | None = None,
    user_source: ErpUserSourcePort | None = None,
    acumatica_info: dict[str, Any] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/integrations/acumatica", tags=["integrations"])
    safe_info = dict(acumatica_info or {})

    @router.get("")
    def acumatica_status() -> dict[str, Any]:
        return {
            "configured": any(
                source is not None
                for source in (project_source, employee_source, user_source)
            ),
            **safe_info,
        }

    @router.post("/employees/sync")
    def sync_employees(
        session: Session = Depends(session_dependency),
    ) -> EmployeeSyncResult:
        if employee_source is None:
            raise ApplicationUnavailableError(
                "La synchronisation des employés Acumatica n'est pas configurée sur ce serveur.",
                code="acumatica_employee_not_configured",
            )
        with performance_phase("compute"):
            return EmployeeSyncService(
                _InstrumentedEmployeeSource(employee_source),
                SqlEmployeeSyncRepository(session),
            ).synchronize()

    @router.post("/users/sync")
    def sync_users(
        session: Session = Depends(session_dependency),
    ) -> ErpUserSyncResult:
        if user_source is None:
            raise ApplicationUnavailableError(
                "La synchronisation des utilisateurs Acumatica n'est pas configurée sur ce serveur.",
                code="acumatica_user_not_configured",
            )
        with performance_phase("compute"):
            return ErpUserSyncService(
                _InstrumentedErpUserSource(user_source),
                SqlErpUserDirectoryRepository(session),
            ).synchronize()

    @router.post("/projects/sync")
    def sync_projects(
        session: Session = Depends(session_dependency),
    ) -> ProjectSyncResult:
        if project_source is None:
            raise ApplicationUnavailableError(
                "L'intégration Acumatica n'est pas configurée sur ce serveur.",
                code="acumatica_not_configured",
            )
        with performance_phase("compute"):
            return ProjectSyncService(
                _InstrumentedProjectSource(project_source),
                SqlProjectSyncRepository(session),
            ).synchronize()

    return router
