from __future__ import annotations

from collections.abc import Iterator
from typing import Callable

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from ..application import (
    CompetencyCatalogService,
    CompetencyCreateCommand,
    CompetencyReadModel,
    CompetencyUpdateCommand,
)
from ..infrastructure.sql import SqlCompetencyCatalogRepository
from .schemas import CompetencyCreateRequest, CompetencyUpdateRequest


SessionProvider = Callable[[], Iterator[Session]]


def _service(session: Session) -> CompetencyCatalogService:
    return CompetencyCatalogService(SqlCompetencyCatalogRepository(session))


def build_competency_router(session_dependency: SessionProvider) -> APIRouter:
    router = APIRouter(prefix="/api/v1/competencies", tags=["competencies"])

    @router.get("")
    def list_competencies(
        q: str | None = Query(default=None),
        active_only: bool = True,
        limit: int = Query(default=200, ge=1, le=500),
        session: Session = Depends(session_dependency),
    ) -> list[CompetencyReadModel]:
        return list(
            _service(session).list(
                query=q,
                active_only=active_only,
                limit=limit,
            )
        )

    @router.post("", status_code=status.HTTP_201_CREATED)
    def create_competency(
        body: CompetencyCreateRequest,
        session: Session = Depends(session_dependency),
    ) -> dict[str, object]:
        return _service(session).create(
            CompetencyCreateCommand(**body.model_dump())
        ).to_dict()

    @router.patch("/{competency_id}")
    def update_competency(
        competency_id: str,
        body: CompetencyUpdateRequest,
        session: Session = Depends(session_dependency),
    ) -> dict[str, object]:
        return _service(session).update(
            CompetencyUpdateCommand(
                competency_id=competency_id,
                **body.model_dump(exclude_unset=True),
            )
        ).to_dict()

    @router.post("/{competency_id}/deactivate")
    def deactivate_competency(
        competency_id: str,
        session: Session = Depends(session_dependency),
    ) -> dict[str, object]:
        return _service(session).deactivate(competency_id).to_dict()

    return router
