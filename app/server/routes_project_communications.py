from __future__ import annotations

from datetime import date
from typing import Any, Callable

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from ..application.communications import CommunicationBatchRecord
from ..application.project_communications import (
    ProjectCommunicationReviewInput,
    ProjectCommunicationService,
    ProjectCommunicationWorkflowPreview,
)
from ..application.security import AuthPrincipal
from ..domain.project_communication import ProjectCommunicationProjection


ProjectCommunicationDependency = Callable[..., Any]


class ProjectReviewBody(BaseModel):
    message_key: str
    include: bool = True
    subject: str | None = None
    body: str | None = None


class PrepareProjectBatchBody(BaseModel):
    week_start: date
    expected_fingerprint: str = Field(min_length=64, max_length=64)
    reviews: list[ProjectReviewBody] = Field(default_factory=list)


def _actor(request: Request) -> str:
    principal: AuthPrincipal | None = getattr(request.state, "auth_principal", None)
    return principal.display_name if principal is not None else "api"


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

    @router.get("/project-preview")
    def project_preview(
        week_start: date,
        service: ProjectCommunicationService = Depends(dependency),
    ) -> ProjectCommunicationWorkflowPreview:
        return service.project_preview(week_start=week_start)

    @router.post("/project-batches", status_code=201)
    def prepare_project_batch(
        body: PrepareProjectBatchBody,
        request: Request,
        service: ProjectCommunicationService = Depends(dependency),
    ) -> CommunicationBatchRecord:
        return service.prepare_project_batch(
            week_start=body.week_start,
            expected_fingerprint=body.expected_fingerprint,
            reviews=tuple(
                ProjectCommunicationReviewInput(
                    message_key=row.message_key,
                    include=row.include,
                    subject=row.subject,
                    body=row.body,
                )
                for row in body.reviews
            ),
            actor_name=_actor(request),
        )

    @router.get("/project-batches")
    def list_project_batches(
        week_start: date | None = None,
        service: ProjectCommunicationService = Depends(dependency),
    ) -> list[CommunicationBatchRecord]:
        return list(service.list_project_batches(week_start=week_start))

    @router.post("/project-batches/{batch_id}/approve")
    def approve_project_batch(
        batch_id: str,
        request: Request,
        service: ProjectCommunicationService = Depends(dependency),
    ) -> CommunicationBatchRecord:
        return service.approve_project_batch(
            batch_id=batch_id,
            actor_name=_actor(request),
        )

    @router.post("/project-batches/{batch_id}/create-drafts")
    def create_project_drafts(
        batch_id: str,
        request: Request,
        service: ProjectCommunicationService = Depends(dependency),
    ) -> CommunicationBatchRecord:
        return service.create_project_drafts(
            batch_id=batch_id,
            actor_name=_actor(request),
        )

    @router.post("/project-batches/{batch_id}/cancel")
    def cancel_project_batch(
        batch_id: str,
        request: Request,
        service: ProjectCommunicationService = Depends(dependency),
    ) -> CommunicationBatchRecord:
        return service.cancel_project_batch(
            batch_id=batch_id,
            actor_name=_actor(request),
        )

    @router.post("/project-batches/{batch_id}/mark-communicated")
    def mark_project_communicated(
        batch_id: str,
        request: Request,
        service: ProjectCommunicationService = Depends(dependency),
    ) -> CommunicationBatchRecord:
        return service.mark_project_communicated(
            batch_id=batch_id,
            actor_name=_actor(request),
        )

    return router
