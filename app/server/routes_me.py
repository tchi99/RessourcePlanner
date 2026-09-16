from __future__ import annotations

from datetime import date
from typing import Any, Callable

from fastapi import APIRouter, Depends, Query, Request

from ..application.query_ports import PlannerQueryPort
from ..application.security import AuthPrincipal
from ..application.technician_schedule import TechnicianScheduleReadModel, TechnicianScheduleService


QueryProvider = Callable[..., Any]


def build_me_router(query_dependency: QueryProvider) -> APIRouter:
    router = APIRouter(prefix="/api/v1/me", tags=["me"])

    @router.get("/schedule")
    def schedule(
        request: Request,
        start: date = Query(),
        end: date = Query(),
        queries: PlannerQueryPort = Depends(query_dependency),
    ) -> TechnicianScheduleReadModel:
        principal: AuthPrincipal = request.state.auth_principal
        return TechnicianScheduleService(queries).read(
            principal=principal,
            start=start,
            end=end,
        )

    return router
