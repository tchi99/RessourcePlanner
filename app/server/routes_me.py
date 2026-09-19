from __future__ import annotations

from datetime import date
from typing import Any, Callable

from fastapi import APIRouter, Depends, Query, Request

from ..application.query_ports import PlannerQueryPort
from ..application.security import AuthPrincipal
from ..application.technician_schedule import TechnicianScheduleReadModel, TechnicianScheduleService
from ..application.user_view_context import (
    UserViewContextReadModel,
    UserViewContextRepositoryPort,
    UserViewContextService,
)


QueryProvider = Callable[..., Any]


def build_me_router(
    query_dependency: QueryProvider,
    user_view_context_dependency: QueryProvider,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/me", tags=["me"])

    @router.get("/schedule")
    def schedule(
        request: Request,
        start: date = Query(),
        end: date = Query(),
        queries: PlannerQueryPort = Depends(query_dependency),
        context_repository: UserViewContextRepositoryPort = Depends(
            user_view_context_dependency
        ),
    ) -> TechnicianScheduleReadModel:
        principal: AuthPrincipal = request.state.auth_principal
        return TechnicianScheduleService(
            queries,
            resource_resolver=context_repository,
        ).read(
            principal=principal,
            start=start,
            end=end,
        )

    @router.get("/context")
    def context(
        request: Request,
        repository: UserViewContextRepositoryPort = Depends(
            user_view_context_dependency
        ),
    ) -> UserViewContextReadModel:
        principal: AuthPrincipal = request.state.auth_principal
        return UserViewContextService(repository).read(principal)

    return router
