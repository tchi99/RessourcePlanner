from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...application.operational_contacts import (
    MaterializedContactContext,
    OperationalContactRepositoryPort,
    RequestLineContactContext,
)
from ...domain.operational_contacts import (
    BusinessContactSnapshot,
    ContactCandidate,
    DIAGNOSTIC_APPROVED_CONTACT_CONTEXT_LEGACY_UNKNOWN,
    DIAGNOSTIC_APPROVED_TASK_PROJECT_MISMATCH,
    DIAGNOSTIC_APPROVED_TASK_REFERENCE_INVALID,
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
from .models import (
    Project,
    RequestLine,
    Resource,
    ResourceRequirement,
    Shift,
    TaskCatalogEntry,
    WorkforceRequest,
)


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
        self._contact_cache: dict[str, BusinessContact] = {}
        self._missing_contact_ids: set[str] = set()

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
        missing = tuple(
            contact_id
            for contact_id in wanted
            if contact_id not in self._contact_cache
            and contact_id not in self._missing_contact_ids
        )
        if missing:
            rows = self._session.scalars(
                select(BusinessContact).where(BusinessContact.id.in_(missing))
            ).all()
            found = {row.id: row for row in rows}
            self._contact_cache.update(found)
            self._missing_contact_ids.update(set(missing) - set(found))
        return {
            contact_id: self._contact_cache[contact_id]
            for contact_id in wanted
            if contact_id in self._contact_cache
        }

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

    def _approved_task_for_requirement(
        self,
        *,
        requirement: ResourceRequirement,
        project: Project,
        diagnostics: list[str],
    ) -> tuple[TaskCatalogEntry | None, bool, tuple[str, ...]]:
        if requirement.approved_contact_context_status == "LEGACY_UNKNOWN":
            context_diagnostics = (
                DIAGNOSTIC_APPROVED_CONTACT_CONTEXT_LEGACY_UNKNOWN,
            )
            diagnostics.extend(context_diagnostics)
            return None, False, context_diagnostics

        if not requirement.approved_task_catalog_item_id:
            return None, True, ()

        task = self._session.get(
            TaskCatalogEntry,
            requirement.approved_task_catalog_item_id,
        )
        if task is None:
            context_diagnostics = (DIAGNOSTIC_APPROVED_TASK_REFERENCE_INVALID,)
            diagnostics.extend(context_diagnostics)
            return None, False, context_diagnostics
        if task.project_number != project.number:
            context_diagnostics = (DIAGNOSTIC_APPROVED_TASK_PROJECT_MISMATCH,)
            diagnostics.extend(context_diagnostics)
            return None, False, context_diagnostics

        if not bool(task.active):
            diagnostics.append(DIAGNOSTIC_TASK_INACTIVE)
        return task, True, ()

    def _materialized_resource(
        self,
        *,
        resource_id: str | None,
        diagnostics: list[str],
    ) -> tuple[Resource | None, bool, tuple[str, ...]]:
        if not resource_id:
            return None, True, ()

        resource = self._session.get(Resource, resource_id)
        if resource is None:
            context_diagnostics = (DIAGNOSTIC_RESOURCE_REFERENCE_INVALID,)
            diagnostics.extend(context_diagnostics)
            return None, False, context_diagnostics
        if not bool(resource.active):
            diagnostics.append(DIAGNOSTIC_RESOURCE_INACTIVE)
        return resource, True, ()

    def _materialized_context(
        self,
        *,
        requirement: ResourceRequirement,
        shift: Shift | None = None,
    ) -> MaterializedContactContext | None:
        project = self._session.get(Project, requirement.project_id)
        if project is None:
            return None

        request = (
            self._session.get(WorkforceRequest, requirement.workforce_request_id)
            if requirement.workforce_request_id
            else None
        )
        diagnostics: list[str] = []
        task, task_context_known, task_context_diagnostics = (
            self._approved_task_for_requirement(
                requirement=requirement,
                project=project,
                diagnostics=diagnostics,
            )
        )

        resource_id = (
            shift.resource_id
            if shift is not None
            else requirement.assigned_resource_id
        )
        resource, resource_context_known, resource_context_diagnostics = (
            self._materialized_resource(
                resource_id=resource_id,
                diagnostics=diagnostics,
            )
        )

        if (
            project.project_manager_contact_id is None
            and (project.project_manager_external_id or project.project_manager_name)
        ):
            diagnostics.append(DIAGNOSTIC_PROJECT_MANAGER_CONTACT_UNMIGRATED)

        contact_ids = (
            requirement.approved_operational_responsible_override_contact_id,
            task.operational_responsible_contact_id if task is not None else None,
            project.project_manager_contact_id,
            resource.coordinator_contact_id if resource is not None else None,
            task.coordinator_contact_id if task is not None else None,
        )
        contacts = self._contacts(contact_ids)
        task_label = f"Tâche {task.task_code}" if task is not None else None
        demand_number = (
            request.legacy_demand_number
            if request is not None
            else None
        )

        return MaterializedContactContext(
            requirement_id=requirement.id,
            shift_id=shift.id if shift is not None else None,
            request_line_id=requirement.source_request_line_id,
            demand_number=demand_number,
            project_id=project.id,
            project_number=project.number,
            approved_request_version=requirement.approved_request_version,
            approved_contact_context_status=(
                requirement.approved_contact_context_status
            ),
            task_id=task.id if task is not None else None,
            task_code=task.task_code if task is not None else None,
            task_label=task.label if task is not None else None,
            resource_id=resource.id if resource is not None else resource_id,
            resource_name=resource.name if resource is not None else None,
            request_override=self._candidate(
                source_type=SOURCE_REQUEST_OVERRIDE,
                source_entity_id=(
                    request.id if request is not None else requirement.workforce_request_id
                ),
                source_label=(
                    f"Demande approuvée {demand_number}"
                    if demand_number
                    else "Demande approuvée"
                ),
                contact_id=(
                    requirement.approved_operational_responsible_override_contact_id
                ),
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
                source_entity_id=resource.id if resource is not None else resource_id,
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
            task_context_known=task_context_known,
            task_context_diagnostics=task_context_diagnostics,
            resource_context_known=resource_context_known,
            resource_context_diagnostics=resource_context_diagnostics,
            diagnostics=_unique(diagnostics),
        )

    def get_resource_requirement_contact_context(
        self,
        requirement_id: str,
    ) -> MaterializedContactContext | None:
        requirement = self._session.get(
            ResourceRequirement,
            str(requirement_id or "").strip(),
        )
        if requirement is None:
            return None
        return self._materialized_context(requirement=requirement)

    def get_shift_contact_context(
        self,
        shift_id: str,
    ) -> MaterializedContactContext | None:
        shift = self._session.get(Shift, str(shift_id or "").strip())
        if shift is None:
            return None
        requirement = self._session.get(
            ResourceRequirement,
            shift.resource_requirement_id,
        )
        if requirement is None:
            return None
        return self._materialized_context(
            requirement=requirement,
            shift=shift,
        )

    def get_request_line_contact_contexts(
        self,
        line_ids: Sequence[str],
    ) -> tuple[RequestLineContactContext, ...]:
        wanted = tuple(
            dict.fromkeys(
                str(line_id or "").strip()
                for line_id in line_ids
                if str(line_id or "").strip()
            )
        )
        if not wanted:
            return ()

        lines = tuple(
            self._session.scalars(
                select(RequestLine).where(RequestLine.id.in_(wanted))
            ).all()
        )
        if not lines:
            return ()
        line_by_id = {line.id: line for line in lines}

        request_ids = {
            line.workforce_request_id
            for line in lines
            if line.workforce_request_id
        }
        requests = {
            row.id: row
            for row in self._session.scalars(
                select(WorkforceRequest).where(
                    WorkforceRequest.id.in_(tuple(request_ids))
                )
            ).all()
        }
        project_ids = {
            request.project_id
            for request in requests.values()
            if request.project_id
        }
        projects = {
            row.id: row
            for row in self._session.scalars(
                select(Project).where(Project.id.in_(tuple(project_ids)))
            ).all()
        }

        direct_task_ids = {
            line.task_catalog_item_id
            for line in lines
            if line.task_catalog_item_id
        }
        tasks = (
            {
                row.id: row
                for row in self._session.scalars(
                    select(TaskCatalogEntry).where(
                        TaskCatalogEntry.id.in_(tuple(direct_task_ids))
                    )
                ).all()
            }
            if direct_task_ids
            else {}
        )
        legacy_project_numbers = {
            projects[request.project_id].number
            for request in requests.values()
            if request.project_id in projects
        }
        legacy_codes = {
            line.erp_task_code for line in lines if line.erp_task_code
        }
        legacy_tasks = (
            self._session.scalars(
                select(TaskCatalogEntry).where(
                    TaskCatalogEntry.project_number.in_(
                        tuple(legacy_project_numbers)
                    ),
                    TaskCatalogEntry.task_code.in_(tuple(legacy_codes)),
                )
            ).all()
            if legacy_project_numbers and legacy_codes
            else []
        )
        legacy_task_by_key = {
            (row.project_number, row.task_code): row for row in legacy_tasks
        }

        resource_ids = {
            line.proposed_resource_id
            for line in lines
            if line.proposed_resource_id
        }
        resources = (
            {
                row.id: row
                for row in self._session.scalars(
                    select(Resource).where(Resource.id.in_(tuple(resource_ids)))
                ).all()
            }
            if resource_ids
            else {}
        )

        resolved: dict[
            str,
            tuple[
                RequestLine,
                WorkforceRequest,
                Project,
                TaskCatalogEntry | None,
                Resource | None,
                tuple[str, ...],
            ],
        ] = {}
        all_contact_ids: list[str | None] = []

        for line_id in wanted:
            line = line_by_id.get(line_id)
            if line is None:
                continue
            request = requests.get(line.workforce_request_id)
            if request is None:
                continue
            project = projects.get(request.project_id)
            if project is None:
                continue

            diagnostics: list[str] = []
            task: TaskCatalogEntry | None = None
            if line.task_catalog_item_id:
                task = tasks.get(line.task_catalog_item_id)
                if task is None:
                    diagnostics.append(DIAGNOSTIC_TASK_REFERENCE_INVALID)
                elif task.project_number != project.number:
                    diagnostics.append(DIAGNOSTIC_TASK_PROJECT_MISMATCH)
                    task = None
            elif line.erp_task_code:
                task = legacy_task_by_key.get(
                    (project.number, line.erp_task_code)
                )
                if task is None:
                    diagnostics.append(DIAGNOSTIC_TASK_REFERENCE_UNRESOLVED)
                else:
                    diagnostics.append(DIAGNOSTIC_TASK_REFERENCE_LEGACY_CODE)

            if task is not None and not bool(task.active):
                diagnostics.append(DIAGNOSTIC_TASK_INACTIVE)

            resource: Resource | None = None
            if line.proposed_resource_id:
                resource = resources.get(line.proposed_resource_id)
                if resource is None:
                    diagnostics.append(DIAGNOSTIC_RESOURCE_REFERENCE_INVALID)
                elif not bool(resource.active):
                    diagnostics.append(DIAGNOSTIC_RESOURCE_INACTIVE)

            if (
                project.project_manager_contact_id is None
                and (
                    project.project_manager_external_id
                    or project.project_manager_name
                )
            ):
                diagnostics.append(
                    DIAGNOSTIC_PROJECT_MANAGER_CONTACT_UNMIGRATED
                )

            all_contact_ids.extend(
                (
                    request.operational_responsible_override_contact_id,
                    (
                        task.operational_responsible_contact_id
                        if task is not None
                        else None
                    ),
                    project.project_manager_contact_id,
                    (
                        resource.coordinator_contact_id
                        if resource is not None
                        else None
                    ),
                    (
                        task.coordinator_contact_id
                        if task is not None
                        else None
                    ),
                )
            )
            resolved[line.id] = (
                line,
                request,
                project,
                task,
                resource,
                _unique(diagnostics),
            )

        contacts = self._contacts(tuple(all_contact_ids))
        result: list[RequestLineContactContext] = []
        for line_id in wanted:
            values = resolved.get(line_id)
            if values is None:
                continue
            line, request, project, task, resource, diagnostics = values
            task_label = None
            if task is not None:
                task_label = f"Tâche {task.task_code}"
            elif line.erp_task_code:
                task_label = f"Tâche {line.erp_task_code}"

            result.append(
                RequestLineContactContext(
                    line_id=line.id,
                    demand_number=request.legacy_demand_number,
                    project_id=project.id,
                    project_number=project.number,
                    task_id=task.id if task is not None else None,
                    task_code=(
                        task.task_code
                        if task is not None
                        else line.erp_task_code
                    ),
                    task_label=(
                        task.label
                        if task is not None
                        else line.erp_task_label
                    ),
                    proposed_resource_id=(
                        resource.id
                        if resource is not None
                        else line.proposed_resource_id
                    ),
                    proposed_resource_name=(
                        resource.name if resource is not None else None
                    ),
                    request_override=self._candidate(
                        source_type=SOURCE_REQUEST_OVERRIDE,
                        source_entity_id=request.id,
                        source_label=(
                            f"Demande {request.legacy_demand_number}"
                            if request.legacy_demand_number
                            else "Demande"
                        ),
                        contact_id=(
                            request.operational_responsible_override_contact_id
                        ),
                        contacts=contacts,
                    ),
                    task_responsible=self._candidate(
                        source_type=SOURCE_TASK_RESPONSIBLE,
                        source_entity_id=(
                            task.id if task is not None else None
                        ),
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
                        source_label=(
                            f"Chargé de projet · {project.number}"
                        ),
                        contact_id=project.project_manager_contact_id,
                        contacts=contacts,
                    ),
                    resource_coordinator=self._candidate(
                        source_type=SOURCE_RESOURCE_COORDINATOR,
                        source_entity_id=(
                            resource.id
                            if resource is not None
                            else line.proposed_resource_id
                        ),
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
                        source_entity_id=(
                            task.id if task is not None else None
                        ),
                        source_label=task_label,
                        contact_id=(
                            task.coordinator_contact_id
                            if task is not None
                            else None
                        ),
                        contacts=contacts,
                    ),
                    diagnostics=diagnostics,
                )
            )
        return tuple(result)

    def get_request_line_contact_context(
        self,
        line_id: str,
    ) -> RequestLineContactContext | None:
        wanted = str(line_id or "").strip()
        rows = self.get_request_line_contact_contexts((wanted,))
        return rows[0] if rows else None

