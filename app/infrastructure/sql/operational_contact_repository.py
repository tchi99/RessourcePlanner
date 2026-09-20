from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...application.operational_contacts import (
    OperationalContactRepositoryPort,
    RequestLineContactContext,
)
from ...domain.operational_contacts import (
    BusinessContactSnapshot,
    ContactCandidate,
    DIAGNOSTIC_PROJECT_MANAGER_CONTACT_UNMIGRATED,
    DIAGNOSTIC_RESOURCE_INACTIVE,
    DIAGNOSTIC_RESOURCE_REFERENCE_INVALID,
    DIAGNOSTIC_TASK_INACTIVE,
    DIAGNOSTIC_TASK_PROJECT_MISMATCH,
    DIAGNOSTIC_TASK_REFERENCE_INVALID,
    DIAGNOSTIC_TASK_REFERENCE_LEGACY_CODE,
    DIAGNOSTIC_TASK_REFERENCE_UNRESOLVED,
    SOURCE_PROJECT_MANAGER,
    SOURCE_REQUEST_OVERRIDE,
    SOURCE_RESOURCE_COORDINATOR,
    SOURCE_TASK_COORDINATOR,
    SOURCE_TASK_RESPONSIBLE,
)
from .business_contact_models import BusinessContact
from .models import Project, RequestLine, Resource, TaskCatalogEntry, WorkforceRequest


def _unique(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def _snapshot(row: BusinessContact | None) -> BusinessContactSnapshot | None:
    if row is None:
        return None
    return BusinessContactSnapshot(
        contact_id=row.id,
        display_name=row.display_name,
        email=row.email,
        phone=row.phone,
        active=bool(row.active),
    )


class SqlOperationalContactRepository(OperationalContactRepositoryPort):
    """Load current RequestLine contact inputs without embedding fallback rules."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def _contacts(self, contact_ids: tuple[str | None, ...]) -> dict[str, BusinessContact]:
        wanted = tuple(
            dict.fromkeys(
                contact_id
                for contact_id in contact_ids
                if contact_id is not None and str(contact_id).strip()
            )
        )
        if not wanted:
            return {}
        rows = self._session.scalars(
            select(BusinessContact).where(BusinessContact.id.in_(wanted))
        ).all()
        return {row.id: row for row in rows}

    @staticmethod
    def _candidate(
        *,
        source_type: str,
        source_entity_id: str | None,
        source_label: str | None,
        contact_id: str | None,
        contacts: dict[str, BusinessContact],
        diagnostics: tuple[str, ...] = (),
    ) -> ContactCandidate:
        return ContactCandidate(
            source_type=source_type,
            source_entity_id=source_entity_id,
            source_label=source_label,
            contact_id=contact_id,
            contact=_snapshot(contacts.get(contact_id)) if contact_id else None,
            diagnostics=diagnostics,
        )

    def _task_for_line(
        self,
        *,
        line: RequestLine,
        project: Project,
        diagnostics: list[str],
    ) -> TaskCatalogEntry | None:
        task: TaskCatalogEntry | None = None
        if line.task_catalog_item_id:
            task = self._session.get(TaskCatalogEntry, line.task_catalog_item_id)
            if task is None:
                diagnostics.append(DIAGNOSTIC_TASK_REFERENCE_INVALID)
                return None
            if task.project_number != project.number:
                diagnostics.append(DIAGNOSTIC_TASK_PROJECT_MISMATCH)
                return None
        elif line.erp_task_code:
            task = self._session.scalar(
                select(TaskCatalogEntry).where(
                    TaskCatalogEntry.project_number == project.number,
                    TaskCatalogEntry.task_code == line.erp_task_code,
                )
            )
            if task is None:
                diagnostics.append(DIAGNOSTIC_TASK_REFERENCE_UNRESOLVED)
                return None
            diagnostics.append(DIAGNOSTIC_TASK_REFERENCE_LEGACY_CODE)

        if task is not None and not bool(task.active):
            diagnostics.append(DIAGNOSTIC_TASK_INACTIVE)
        return task

    def _resource_for_line(
        self,
        *,
        line: RequestLine,
        diagnostics: list[str],
    ) -> Resource | None:
        if not line.proposed_resource_id:
            return None
        resource = self._session.get(Resource, line.proposed_resource_id)
        if resource is None:
            diagnostics.append(DIAGNOSTIC_RESOURCE_REFERENCE_INVALID)
            return None
        if not bool(resource.active):
            diagnostics.append(DIAGNOSTIC_RESOURCE_INACTIVE)
        return resource

    def get_request_line_contact_context(
        self,
        line_id: str,
    ) -> RequestLineContactContext | None:
        line = self._session.get(RequestLine, str(line_id or "").strip())
        if line is None:
            return None

        request = self._session.get(WorkforceRequest, line.workforce_request_id)
        if request is None:
            return None
        project = self._session.get(Project, request.project_id)
        if project is None:
            return None

        diagnostics: list[str] = []
        task = self._task_for_line(
            line=line,
            project=project,
            diagnostics=diagnostics,
        )
        resource = self._resource_for_line(
            line=line,
            diagnostics=diagnostics,
        )

        if (
            project.project_manager_contact_id is None
            and (project.project_manager_external_id or project.project_manager_name)
        ):
            diagnostics.append(DIAGNOSTIC_PROJECT_MANAGER_CONTACT_UNMIGRATED)

        contact_ids = (
            request.operational_responsible_override_contact_id,
            task.operational_responsible_contact_id if task is not None else None,
            project.project_manager_contact_id,
            resource.coordinator_contact_id if resource is not None else None,
            task.coordinator_contact_id if task is not None else None,
        )
        contacts = self._contacts(contact_ids)

        task_label = None
        if task is not None:
            task_label = f"Tâche {task.task_code}"
        elif line.erp_task_code:
            task_label = f"Tâche {line.erp_task_code}"

        return RequestLineContactContext(
            line_id=line.id,
            demand_number=request.legacy_demand_number,
            project_id=project.id,
            project_number=project.number,
            task_id=task.id if task is not None else None,
            task_code=task.task_code if task is not None else line.erp_task_code,
            task_label=task.label if task is not None else line.erp_task_label,
            proposed_resource_id=resource.id if resource is not None else line.proposed_resource_id,
            proposed_resource_name=resource.name if resource is not None else None,
            request_override=self._candidate(
                source_type=SOURCE_REQUEST_OVERRIDE,
                source_entity_id=request.id,
                source_label=(
                    f"Demande {request.legacy_demand_number}"
                    if request.legacy_demand_number
                    else "Demande"
                ),
                contact_id=request.operational_responsible_override_contact_id,
                contacts=contacts,
            ),
            task_responsible=self._candidate(
                source_type=SOURCE_TASK_RESPONSIBLE,
                source_entity_id=task.id if task is not None else None,
                source_label=task_label,
                contact_id=(
                    task.operational_responsible_contact_id
                    if task is not None
                    else None
                ),
                contacts=contacts,
            ),
            project_manager=self._candidate(
                source_type=SOURCE_PROJECT_MANAGER,
                source_entity_id=project.id,
                source_label=f"Chargé de projet · {project.number}",
                contact_id=project.project_manager_contact_id,
                contacts=contacts,
            ),
            resource_coordinator=self._candidate(
                source_type=SOURCE_RESOURCE_COORDINATOR,
                source_entity_id=resource.id if resource is not None else None,
                source_label=(
                    f"Ressource {resource.name}"
                    if resource is not None
                    else None
                ),
                contact_id=(
                    resource.coordinator_contact_id
                    if resource is not None
                    else None
                ),
                contacts=contacts,
            ),
            task_coordinator=self._candidate(
                source_type=SOURCE_TASK_COORDINATOR,
                source_entity_id=task.id if task is not None else None,
                source_label=task_label,
                contact_id=task.coordinator_contact_id if task is not None else None,
                contacts=contacts,
            ),
            diagnostics=_unique(diagnostics),
        )
