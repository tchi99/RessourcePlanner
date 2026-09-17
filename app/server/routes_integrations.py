from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Callable

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..application import ProjectSourcePort, ProjectSyncResult, ProjectSyncService
from ..application.errors import ApplicationUnavailableError
from ..infrastructure.sql import SqlProjectSyncRepository
from .performance import performance_phase, record_external_call, record_external_items


SessionProvider = Callable[[], Iterator[Session]]


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
    acumatica_info: dict[str, Any] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/integrations/acumatica", tags=["integrations"])
    safe_info = dict(acumatica_info or {})

    @router.get("")
    def acumatica_status() -> dict[str, Any]:
        return {
            "configured": project_source is not None,
            **safe_info,
        }

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
