from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Callable

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..application.operational_contacts import OperationalContactService
from ..application.business_contact_admin import (
    BusinessContactAdminService,
    BusinessContactRecord,
    ContactLinkRecord,
    DemandOverrideMutationResult,
)
from ..application.security import AuthPrincipal
from ..infrastructure.sql.operational_contact_repository import SqlOperationalContactRepository


BusinessContactProvider = Callable[..., Any]
SessionProvider = Callable[[], Iterator[Session]]


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BusinessContactCreateRequest(StrictRequest):
    display_name: str = Field(min_length=1)
    email: str | None = None
    phone: str | None = None
    active: bool = True
    source: str = Field(default="LOCAL", min_length=1)
    external_system: str | None = None
    external_entity: str | None = None
    external_id: str | None = None


class BusinessContactUpdateRequest(StrictRequest):
    display_name: str | None = None
    email: str | None = None
    phone: str | None = None
    active: bool | None = None
    source: str | None = None
    external_system: str | None = None
    external_entity: str | None = None
    external_id: str | None = None
    expected_version: int | None = Field(default=None, ge=1)

    @field_validator("display_name", "active", "source", mode="before")
    @classmethod
    def reject_null_required_fields(cls, value: object) -> object:
        if value is None:
            raise ValueError("Ce champ ne peut pas être null; omets-le pour ne pas le modifier.")
        return value


class ContactLinkRequest(StrictRequest):
    contact_id: str | None = None

    @model_validator(mode="after")
    def require_explicit_contact_id(self) -> "ContactLinkRequest":
        if "contact_id" not in self.model_fields_set:
            raise ValueError("contact_id doit être fourni explicitement; null retire le rattachement.")
        return self


class TaskContactLinksRequest(StrictRequest):
    operational_responsible_contact_id: str | None = None
    coordinator_contact_id: str | None = None


class DemandOperationalResponsibleRequest(StrictRequest):
    contact_id: str | None = None
    expected_version: int = Field(ge=1)

    @model_validator(mode="after")
    def require_explicit_contact_id(self) -> "DemandOperationalResponsibleRequest":
        if "contact_id" not in self.model_fields_set:
            raise ValueError("contact_id doit être fourni explicitement; null retire l'override.")
        return self


def _contact_payload(row: BusinessContactRecord) -> dict[str, object]:
    return {
        "id": row.id,
        "display_name": row.display_name,
        "email": row.email,
        "phone": row.phone,
        "active": row.active,
        "source": row.source,
        "external_system": row.external_system,
        "external_entity": row.external_entity,
        "external_id": row.external_id,
        "version": row.version,
    }


def _link_payload(row: ContactLinkRecord) -> dict[str, object]:
    return {
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "entity_label": row.entity_label,
        "project_manager_contact_id": row.project_manager_contact_id,
        "operational_responsible_contact_id": row.operational_responsible_contact_id,
        "coordinator_contact_id": row.coordinator_contact_id,
        "operational_responsible_override_contact_id": (
            row.operational_responsible_override_contact_id
        ),
        "aggregate_version": row.aggregate_version,
        "status": row.status,
    }


def _override_payload(row: DemandOverrideMutationResult) -> dict[str, object]:
    return {
        "demand_number": row.demand_number,
        "contact_id": row.contact_id,
        "version": row.version,
        "status": row.status,
        "reapproval_required": row.reapproval_required,
        "changed": row.changed,
    }


def build_business_contact_router(
    dependency: BusinessContactProvider,
    session_dependency: SessionProvider,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["business-contacts"])

    @router.get("/request-lines/{line_id}/contact-resolution")
    def request_line_contact_resolution(
        line_id: str,
        session: Session = Depends(session_dependency),
    ) -> dict[str, object]:
        row = OperationalContactService(
            SqlOperationalContactRepository(session)
        ).resolve_request_line(line_id)
        return {
            "line_id": row.line_id,
            "demand_number": row.demand_number,
            "project_number": row.project_number,
            "task_id": row.task_id,
            "task_code": row.task_code,
            "task_label": row.task_label,
            "proposed_resource_id": row.proposed_resource_id,
            "proposed_resource_name": row.proposed_resource_name,
            "operational_responsible": {
                "status": row.operational_responsible.status,
                "contact_id": row.operational_responsible.contact_id,
                "display_name": row.operational_responsible.display_name,
                "email": row.operational_responsible.email,
                "phone": row.operational_responsible.phone,
                "source_type": row.operational_responsible.source_type,
                "source_entity_id": row.operational_responsible.source_entity_id,
                "source_label": row.operational_responsible.source_label,
                "diagnostics": list(row.operational_responsible.diagnostics),
            },
            "coordinator": {
                "status": row.coordinator.status,
                "contact_id": row.coordinator.contact_id,
                "display_name": row.coordinator.display_name,
                "email": row.coordinator.email,
                "phone": row.coordinator.phone,
                "source_type": row.coordinator.source_type,
                "source_entity_id": row.coordinator.source_entity_id,
                "source_label": row.coordinator.source_label,
                "diagnostics": list(row.coordinator.diagnostics),
            },
            "diagnostics": list(row.diagnostics),
        }

    @router.get("/business-contacts")
    def list_contacts(
        active_only: bool = False,
        service: BusinessContactAdminService = Depends(dependency),
    ) -> list[dict[str, object]]:
        return [
            _contact_payload(row)
            for row in service.list_contacts(active_only=active_only)
        ]

    @router.post(
        "/business-contacts",
        status_code=status.HTTP_201_CREATED,
    )
    def create_contact(
        body: BusinessContactCreateRequest,
        service: BusinessContactAdminService = Depends(dependency),
    ) -> dict[str, object]:
        return _contact_payload(service.create_contact(**body.model_dump()))

    @router.patch("/business-contacts/{contact_id}")
    def update_contact(
        contact_id: str,
        body: BusinessContactUpdateRequest,
        service: BusinessContactAdminService = Depends(dependency),
    ) -> dict[str, object]:
        values = body.model_dump(exclude_unset=True)
        expected_version = values.pop("expected_version", None)
        return _contact_payload(
            service.update_contact(
                contact_id,
                values,
                expected_version=expected_version,
            )
        )

    @router.get("/projects/{project_number}/business-contacts")
    def project_contact_link(
        project_number: str,
        service: BusinessContactAdminService = Depends(dependency),
    ) -> dict[str, object]:
        return _link_payload(service.project_link(project_number))

    @router.patch("/projects/{project_number}/project-manager-contact")
    def set_project_manager_contact(
        project_number: str,
        body: ContactLinkRequest,
        service: BusinessContactAdminService = Depends(dependency),
    ) -> dict[str, object]:
        return _link_payload(
            service.set_project_manager_contact(project_number, body.contact_id)
        )

    @router.get("/task-catalog/{task_id}/business-contacts")
    def task_contact_link(
        task_id: str,
        service: BusinessContactAdminService = Depends(dependency),
    ) -> dict[str, object]:
        return _link_payload(service.task_link(task_id))

    @router.patch("/task-catalog/{task_id}/business-contacts")
    def set_task_contacts(
        task_id: str,
        body: TaskContactLinksRequest,
        service: BusinessContactAdminService = Depends(dependency),
    ) -> dict[str, object]:
        changes = {
            field: getattr(body, field)
            for field in body.model_fields_set
            if field in {
                "operational_responsible_contact_id",
                "coordinator_contact_id",
            }
        }
        return _link_payload(service.set_task_contacts(task_id, changes))

    @router.get("/resources/{resource_id}/business-contacts")
    def resource_contact_link(
        resource_id: str,
        service: BusinessContactAdminService = Depends(dependency),
    ) -> dict[str, object]:
        return _link_payload(service.resource_link(resource_id))

    @router.patch("/resources/{resource_id}/coordinator-contact")
    def set_resource_coordinator(
        resource_id: str,
        body: ContactLinkRequest,
        service: BusinessContactAdminService = Depends(dependency),
    ) -> dict[str, object]:
        return _link_payload(
            service.set_resource_coordinator(resource_id, body.contact_id)
        )

    @router.get("/demands/{demand_number}/business-contacts")
    def demand_contact_link(
        demand_number: str,
        service: BusinessContactAdminService = Depends(dependency),
    ) -> dict[str, object]:
        return _link_payload(service.demand_link(demand_number))

    @router.patch("/demands/{demand_number}/operational-responsible")
    def set_demand_operational_responsible(
        demand_number: str,
        body: DemandOperationalResponsibleRequest,
        request: Request,
        service: BusinessContactAdminService = Depends(dependency),
    ) -> dict[str, object]:
        principal: AuthPrincipal = request.state.auth_principal
        return _override_payload(
            service.set_demand_override(
                demand_number,
                body.contact_id,
                expected_version=body.expected_version,
                actor_name=principal.display_name,
            )
        )

    return router
