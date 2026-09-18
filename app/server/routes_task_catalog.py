from __future__ import annotations

from collections.abc import Iterator
from typing import Callable

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..application.task_catalog import TaskCatalogItem
from ..infrastructure.sql.task_catalog_repository import SqlTaskCatalogRepository


SessionProvider = Callable[[], Iterator[Session]]


def build_task_catalog_router(session_dependency: SessionProvider) -> APIRouter:
    router = APIRouter(prefix="/api/v1/task-catalog", tags=["task-catalog"])

    @router.get("")
    def search_task_catalog(
        project_number: str | None = Query(default=None),
        q: str | None = Query(default=None),
        active_only: bool = True,
        limit: int = Query(default=200, ge=1, le=500),
        session: Session = Depends(session_dependency),
    ) -> list[TaskCatalogItem]:
        return list(
            SqlTaskCatalogRepository(session).search(
                project_number=project_number,
                query=q,
                active_only=active_only,
                limit=limit,
            )
        )

    return router
