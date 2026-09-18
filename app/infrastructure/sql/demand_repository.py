from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from ...application.read_models import DemandReadModel
from ...application.repository_ports import DemandRepositoryPort
from .base import utc_now
from .models import (
    Project,
    Resource,
    TaskCatalogEntry,
    WorkforceRequest,
    WorkforceRequestCompetency,
    WorkforceRequestHistory,
    WorkPackage,
)


_DEMAND_NUMBER_RE = re.compile(r"^DMO-(\d{4})-(\d+)$", re.IGNORECASE)


def _text(value: object) -> str:
    return str(value or "").strip()


def _optional_text(value: object) -> str | None:
    value_text = _text(value)
    return value_text or None


def _decimal(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    return Decimal(str(value).replace(",", "."))


class SqlDemandRepository(DemandRepositoryPort):
    """SQLAlchemy implementation of the workforce-demand persistence port.

    The repository participates in the caller's transaction. It flushes mutations so
    constraints fail inside the use case, but it never commits or rolls back itself.
    """

    def __init__(self, session: Session, *, actor_name: str = "") -> None:
        self._session = session
        self._actor_name = _text(actor_name)

    def _read_model(
        self,
        request: WorkforceRequest,
        project: Project,
        work_package: WorkPackage | None,
        proposed_resource: Resource | None,
    ) -> DemandReadModel:
        return DemandReadModel(
            # During the first SQL cutover the existing NoDemande is preserved in
            # legacy_demand_number. A dedicated business-number column can replace
            # this compatibility name later without changing the application port.
            number=_text(request.legacy_demand_number) or request.id,
            status=_text(request.status),
            project_number=_optional_text(project.number),
            project_name=_optional_text(project.name),
            client=_optional_text(project.client),
            project_manager=_optional_text(project.project_manager_name),
            requester=_optional_text(request.requester_name),
            priority=_optional_text(request.priority),
            confirmation=_optional_text(request.confirmation),
            desired_start=request.desired_start,
            desired_end=request.desired_end,
            description=_optional_text(request.description),
            work_package_ref=(
                _optional_text(work_package.legacy_effort_id) or work_package.id
                if work_package is not None
                else None
            ),
            work_package_name=(
                _optional_text(work_package.name) if work_package is not None else None
            ),
            task_code=_optional_text(request.erp_task_code),
            task_label=_optional_text(request.erp_task_label),
            resource_count=max(int(request.resource_count or 1), 1),
            required_competencies=_optional_text(request.required_competencies),
            required_competency_ids=tuple(
                self._session.scalars(
                    select(WorkforceRequestCompetency.competency_id).where(
                        WorkforceRequestCompetency.workforce_request_id == request.id
                    )
                ).all()
            ),
            estimated_hours=(
                float(request.estimated_hours)
                if request.estimated_hours is not None
                else None
            ),
            estimated_days=(
                float(request.estimated_days)
                if request.estimated_days is not None
                else None
            ),
            proposed_resource=(
                _optional_text(proposed_resource.name)
                if proposed_resource is not None
                else None
            ),
        )

    def _row_query(self):
        proposed_resource = aliased(Resource)
        return (
            select(WorkforceRequest, Project, WorkPackage, proposed_resource)
            .join(Project, WorkforceRequest.project_id == Project.id)
            .outerjoin(WorkPackage, WorkforceRequest.work_package_id == WorkPackage.id)
            .outerjoin(
                proposed_resource,
                WorkforceRequest.proposed_resource_id == proposed_resource.id,
            )
        )

    def list(self) -> Sequence[DemandReadModel]:
        rows = self._session.execute(
            self._row_query().order_by(
                WorkforceRequest.desired_start,
                WorkforceRequest.legacy_demand_number,
                WorkforceRequest.id,
            )
        ).all()
        return tuple(
            self._read_model(request, project, work_package, proposed_resource)
            for request, project, work_package, proposed_resource in rows
        )

    def get(self, number: str) -> DemandReadModel | None:
        wanted = _text(number)
        if not wanted:
            return None
        row = self._session.execute(
            self._row_query().where(
                (WorkforceRequest.legacy_demand_number == wanted)
                | (WorkforceRequest.id == wanted)
            )
        ).one_or_none()
        if row is None:
            return None
        request, project, work_package, proposed_resource = row
        return self._read_model(request, project, work_package, proposed_resource)

    def _request(self, number: str) -> WorkforceRequest:
        wanted = _text(number)
        request = self._session.scalar(
            select(WorkforceRequest).where(
                (WorkforceRequest.legacy_demand_number == wanted)
                | (WorkforceRequest.id == wanted)
            )
        )
        if request is None:
            raise KeyError(f"Demande {wanted} introuvable")
        return request

    def _project(self, number: object) -> Project:
        project_number = _text(number)
        project = self._session.scalar(
            select(Project).where(Project.number == project_number)
        )
        if project is None:
            raise KeyError(f"Projet {project_number} introuvable")
        return project

    def _work_package(
        self,
        reference: object,
        *,
        project_id: str,
    ) -> WorkPackage | None:
        work_package_ref = _text(reference)
        if not work_package_ref:
            return None
        work_package = self._session.scalar(
            select(WorkPackage).where(
                (WorkPackage.id == work_package_ref)
                | (WorkPackage.legacy_effort_id == work_package_ref)
            )
        )
        if work_package is None:
            raise KeyError(f"Plage moyen terme {work_package_ref} introuvable")
        if work_package.project_id != project_id:
            raise ValueError(
                f"La plage moyen terme {work_package_ref} n'appartient pas au projet sélectionné."
            )
        return work_package

    def _task(self, code: object, *, project_number: str) -> TaskCatalogEntry | None:
        task_code = _text(code)
        if not task_code:
            return None
        task = self._session.scalar(
            select(TaskCatalogEntry).where(
                TaskCatalogEntry.project_number == _text(project_number),
                TaskCatalogEntry.task_code == task_code,
            )
        )
        if task is None:
            raise KeyError(
                f"Tâche ERP {_text(project_number)}/{task_code} introuvable"
            )
        if not task.active:
            raise ValueError(
                f"La tâche ERP {_text(project_number)}/{task_code} est inactive."
            )
        return task

    def _resource(self, name: object) -> Resource | None:
        resource_name = _text(name)
        if not resource_name:
            return None
        resource = self._session.scalar(
            select(Resource).where(Resource.name == resource_name)
        )
        if resource is None:
            raise KeyError(f"Ressource {resource_name} introuvable")
        return resource

    def _next_request_number(self) -> str:
        year = date.today().year
        prefix = f"DMO-{year}-"
        numbers = self._session.scalars(
            select(WorkforceRequest.legacy_demand_number).where(
                WorkforceRequest.legacy_demand_number.like(f"{prefix}%")
            )
        ).all()
        max_sequence = 0
        for number in numbers:
            match = _DEMAND_NUMBER_RE.match(_text(number))
            if match and int(match.group(1)) == year:
                max_sequence = max(max_sequence, int(match.group(2)))
        return f"DMO-{year}-{max_sequence + 1:04d}"

    def create(self, values: Mapping[str, Any], *, submit: bool = False) -> str:
        project = self._project(values.get("NumeroProjet"))
        work_package = self._work_package(
            values.get("SourceEffortID"),
            project_id=project.id,
        )
        task = self._task(
            values.get("TaskCode"),
            project_number=project.number,
        )
        proposed_resource = self._resource(values.get("TechnicienPropose"))
        number = self._next_request_number()
        status = "Soumise" if submit else "Brouillon"

        request = WorkforceRequest(
            legacy_demand_number=number,
            project_id=project.id,
            work_package_id=work_package.id if work_package is not None else None,
            erp_task_code=task.task_code if task is not None else None,
            erp_task_label=task.label if task is not None else None,
            # An authorized caller may explicitly name the requester. When omitted,
            # preserve the historical behavior and default to the authenticated actor.
            requester_name=_optional_text(values.get("Demandeur")) or self._actor_name or None,
            request_type=_text(values.get("TypeDemande")) or "Projet",
            priority=_text(values.get("Priorite")) or "Normale",
            confirmation=_text(values.get("Confirmation")) or "Confirmée",
            desired_start=values.get("DateDebutSouhaitee"),
            desired_end=values.get("DateFinSouhaitee"),
            description=_optional_text(values.get("Description")),
            site_client=_optional_text(values.get("SiteClient")),
            location=_optional_text(values.get("Lieu")),
            resource_count=int(values.get("NombreRessources") or 1),
            required_competencies=_optional_text(values.get("CompetencesRequises")),
            estimated_hours=_decimal(values.get("TempsEstimeHeures")),
            estimated_days=_decimal(values.get("TempsEstimeJours")),
            proposed_resource_id=proposed_resource.id if proposed_resource else None,
            status=status,
        )
        self._session.add(request)
        self._session.flush()
        self._append_history(
            request,
            action="Création",
            comment="Demande créée et soumise" if submit else "Demande créée",
        )
        self._session.flush()
        return number

    def update(
        self,
        number: str,
        updates: Mapping[str, Any],
        *,
        action: str,
        comment: str = "",
    ) -> None:
        request = self._request(number)

        project_changed = "NumeroProjet" in updates
        if project_changed:
            request.project_id = self._project(updates.get("NumeroProjet")).id

        if "SourceEffortID" in updates:
            work_package = self._work_package(
                updates.get("SourceEffortID"),
                project_id=request.project_id,
            )
            request.work_package_id = work_package.id if work_package is not None else None
        elif project_changed and request.work_package_id:
            current_work_package = self._session.get(WorkPackage, request.work_package_id)
            if (
                current_work_package is None
                or current_work_package.project_id != request.project_id
            ):
                # A WorkPackage is project-owned. Changing project without explicitly
                # choosing a compatible WorkPackage must not leave a cross-project link.
                request.work_package_id = None

        if "TaskCode" in updates:
            project = self._session.get(Project, request.project_id)
            if project is None:
                raise KeyError("Projet de la demande introuvable")
            task = self._task(
                updates.get("TaskCode"),
                project_number=project.number,
            )
            request.erp_task_code = task.task_code if task is not None else None
            request.erp_task_label = task.label if task is not None else None
        elif project_changed:
            # A task code is project-scoped in the ERP export. Never keep a task
            # silently attached when the demand moves to another project.
            request.erp_task_code = None
            request.erp_task_label = None

        if "Demandeur" in updates:
            request.requester_name = _optional_text(updates.get("Demandeur"))
        if "TypeDemande" in updates:
            request.request_type = _text(updates.get("TypeDemande")) or "Projet"
        if "Priorite" in updates:
            request.priority = _text(updates.get("Priorite")) or "Normale"
        if "Confirmation" in updates:
            request.confirmation = _text(updates.get("Confirmation")) or "Confirmée"
        if "DateDebutSouhaitee" in updates:
            request.desired_start = updates.get("DateDebutSouhaitee")
        if "DateFinSouhaitee" in updates:
            request.desired_end = updates.get("DateFinSouhaitee")
        if "Description" in updates:
            request.description = _optional_text(updates.get("Description"))
        if "SiteClient" in updates:
            request.site_client = _optional_text(updates.get("SiteClient"))
        if "Lieu" in updates:
            request.location = _optional_text(updates.get("Lieu"))
        if "NombreRessources" in updates:
            request.resource_count = int(updates.get("NombreRessources") or 1)
        if "CompetencesRequises" in updates:
            request.required_competencies = _optional_text(
                updates.get("CompetencesRequises")
            )
        if "TempsEstimeHeures" in updates:
            request.estimated_hours = _decimal(updates.get("TempsEstimeHeures"))
        if "TempsEstimeJours" in updates:
            request.estimated_days = _decimal(updates.get("TempsEstimeJours"))
        if "TechnicienPropose" in updates:
            proposed = self._resource(updates.get("TechnicienPropose"))
            request.proposed_resource_id = proposed.id if proposed else None
        if "Statut" in updates:
            request.status = _text(updates.get("Statut"))
        if "ApprouvePar" in updates:
            request.approved_by_name = _optional_text(updates.get("ApprouvePar"))
        if "DateApprobation" in updates:
            approved_at = updates.get("DateApprobation")
            request.approved_at = approved_at if isinstance(approved_at, datetime) else None
        if "CommentaireApprobation" in updates:
            request.approval_comment = _optional_text(
                updates.get("CommentaireApprobation")
            )

        # NomProjet/Client/ChargeProjet intentionally remain project-owned. They are
        # projected from projects and will ultimately be mastered by Acumatica.
        self._session.flush()
        self._append_history(
            request,
            action=_text(action) or "Modification",
            comment=_text(comment),
        )
        self._session.flush()

    def _append_history(
        self,
        request: WorkforceRequest,
        *,
        action: str,
        comment: str,
    ) -> None:
        self._session.add(
            WorkforceRequestHistory(
                workforce_request_id=request.id,
                action=action,
                status=request.status,
                comment=comment or None,
                actor_name=self._actor_name or None,
                occurred_at=utc_now(),
            )
        )
