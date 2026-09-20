from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..domain.operational_contacts import (
    ContactCandidate,
    ContactResolution,
    resolve_coordinator,
    resolve_operational_responsible,
)
from .errors import ApplicationNotFoundError, call_application_port


@dataclass(frozen=True, slots=True)
class RequestLineContactContext:
    line_id: str
    demand_number: str | None
    project_id: str
    project_number: str
    task_id: str | None
    task_code: str | None
    task_label: str | None
    proposed_resource_id: str | None
    proposed_resource_name: str | None
    request_override: ContactCandidate
    task_responsible: ContactCandidate
    project_manager: ContactCandidate
    resource_coordinator: ContactCandidate
    task_coordinator: ContactCandidate
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RequestLineContactResolution:
    line_id: str
    demand_number: str | None
    project_number: str
    task_id: str | None
    task_code: str | None
    task_label: str | None
    proposed_resource_id: str | None
    proposed_resource_name: str | None
    operational_responsible: ContactResolution
    coordinator: ContactResolution
    diagnostics: tuple[str, ...] = ()


class OperationalContactRepositoryPort(Protocol):
    def get_request_line_contact_context(
        self,
        line_id: str,
    ) -> RequestLineContactContext | None: ...


class OperationalContactService:
    """Resolve current request-line contacts without reading approved planning state."""

    def __init__(self, repository: OperationalContactRepositoryPort) -> None:
        self._repository = repository

    def resolve_request_line(self, line_id: str) -> RequestLineContactResolution:
        context = call_application_port(
            lambda: self._repository.get_request_line_contact_context(line_id),
            code_prefix="operational_contact_read",
            context={"line_id": line_id},
        )
        if context is None:
            raise ApplicationNotFoundError(
                "La ligne de demande est introuvable.",
                code="request_line_not_found",
                context={"line_id": line_id},
            )

        responsible = resolve_operational_responsible(
            request_override=context.request_override,
            task_responsible=context.task_responsible,
            project_manager=context.project_manager,
        )
        coordinator = resolve_coordinator(
            resource_coordinator=context.resource_coordinator,
            task_coordinator=context.task_coordinator,
        )
        return RequestLineContactResolution(
            line_id=context.line_id,
            demand_number=context.demand_number,
            project_number=context.project_number,
            task_id=context.task_id,
            task_code=context.task_code,
            task_label=context.task_label,
            proposed_resource_id=context.proposed_resource_id,
            proposed_resource_name=context.proposed_resource_name,
            operational_responsible=responsible,
            coordinator=coordinator,
            diagnostics=context.diagnostics,
        )
