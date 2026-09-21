from __future__ import annotations

from datetime import date
from typing import Any, Callable

from fastapi import APIRouter, Depends

from ..application.project_communications import ProjectCommunicationService
from ..domain.project_communication import ProjectCommunicationProjection


ProjectCommunicationDependency = Callable[..., Any]


def build_project_communication_router(
    dependency: ProjectCommunicationDependency,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/communications", tags=["communications"])

    @router.get("/project-projection")
    def project_projection(
        week_start: date,
        service: ProjectCommunicationService = Depends(dependency),
    ) -> ProjectCommunicationProjection:
        return service.project_projection(week_start=week_start)

    return router
