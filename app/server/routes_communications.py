from __future__ import annotations

from datetime import date
from typing import Any, Callable

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from ..application.communications import (
    CommunicationBatchRecord,
    CommunicationContactRecord,
    CommunicationPreview,
    CommunicationReviewInput,
    CommunicationService,
)
from ..application.security import AuthPrincipal


CommunicationDependency = Callable[..., Any]


class ContactUpdateBody(BaseModel):
    audience: str
    display_name: str
    email: str | None = None
    active: bool = True


class ReviewBody(BaseModel):
    audience: str
    recipient_id: str
    include: bool = True
    subject: str | None = None
    body: str | None = None


class PrepareBatchBody(BaseModel):
    week_start: date
    expected_fingerprint: str = Field(min_length=64, max_length=64)
    reviews: list[ReviewBody] = Field(default_factory=list)


def _actor(request: Request) -> str:
    principal: AuthPrincipal | None = getattr(request.state, "auth_principal", None)
    return principal.display_name if principal is not None else "api"


def build_communication_router(service_dependency: CommunicationDependency) -> APIRouter:
    router = APIRouter(prefix="/api/v1/communications", tags=["communications"])

    @router.get("/contacts")
    def list_contacts(
        service: CommunicationService = Depends(service_dependency),
    ) -> list[CommunicationContactRecord]:
        return list(service.list_contacts())

    @router.put("/contacts/{recipient_id}")
    def update_contact(
        recipient_id: str,
        body: ContactUpdateBody,
        service: CommunicationService = Depends(service_dependency),
    ) -> CommunicationContactRecord:
        return service.update_contact(
            recipient_id=recipient_id,
            audience=body.audience,
            display_name=body.display_name,
            email=body.email,
            active=body.active,
        )

    @router.get("/preview")
    def preview(
        week_start: date,
        service: CommunicationService = Depends(service_dependency),
    ) -> CommunicationPreview:
        return service.preview(week_start=week_start)

    @router.post("/batches", status_code=201)
    def prepare_batch(
        body: PrepareBatchBody,
        request: Request,
        service: CommunicationService = Depends(service_dependency),
    ) -> CommunicationBatchRecord:
        return service.prepare(
            week_start=body.week_start,
            expected_fingerprint=body.expected_fingerprint,
            reviews=tuple(
                CommunicationReviewInput(
                    audience=row.audience,
                    recipient_id=row.recipient_id,
                    include=row.include,
                    subject=row.subject,
                    body=row.body,
                )
                for row in body.reviews
            ),
            actor_name=_actor(request),
        )

    @router.get("/batches")
    def list_batches(
        week_start: date | None = None,
        service: CommunicationService = Depends(service_dependency),
    ) -> list[CommunicationBatchRecord]:
        return list(service.list_batches(week_start=week_start))

    @router.post("/batches/{batch_id}/approve")
    def approve_batch(
        batch_id: str,
        request: Request,
        service: CommunicationService = Depends(service_dependency),
    ) -> CommunicationBatchRecord:
        return service.approve(batch_id=batch_id, actor_name=_actor(request))

    @router.post("/batches/{batch_id}/create-drafts")
    def create_drafts(
        batch_id: str,
        request: Request,
        service: CommunicationService = Depends(service_dependency),
    ) -> CommunicationBatchRecord:
        return service.create_drafts(batch_id=batch_id, actor_name=_actor(request))

    @router.post("/batches/{batch_id}/cancel")
    def cancel_batch(
        batch_id: str,
        request: Request,
        service: CommunicationService = Depends(service_dependency),
    ) -> CommunicationBatchRecord:
        return service.cancel(batch_id=batch_id, actor_name=_actor(request))

    @router.post("/batches/{batch_id}/mark-communicated")
    def mark_communicated(
        batch_id: str,
        request: Request,
        service: CommunicationService = Depends(service_dependency),
    ) -> CommunicationBatchRecord:
        return service.mark_communicated(batch_id=batch_id, actor_name=_actor(request))

    return router
