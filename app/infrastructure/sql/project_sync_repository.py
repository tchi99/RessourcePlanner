from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...application.errors import ApplicationConflictError, ApplicationValidationError
from ...application.project_sync import ExternalProjectRecord, ProjectSyncRepositoryPort
from .models import Project


def _text(value: object) -> str:
    return str(value or "").strip()


def _optional_text(value: object) -> str | None:
    text = _text(value)
    return text or None


class SqlProjectSyncRepository(ProjectSyncRepositoryPort):
    """Idempotent ERP-project upsert for the local operational project table."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_external_project(self, project: ExternalProjectRecord) -> str:
        external_id = _text(project.external_id)
        number = _text(project.number)
        name = _text(project.name)
        if not number:
            raise ApplicationValidationError(
                "Un numéro de projet est requis pour synchroniser un projet.",
                code="project_sync_number_required",
                context={"erp_external_id": external_id or None},
            )
        if not name:
            raise ApplicationValidationError(
                "Un nom de projet est requis pour synchroniser un projet.",
                code="project_sync_name_required",
                context={"erp_external_id": external_id or None, "project_number": number},
            )

        by_external = (
            self._session.scalar(select(Project).where(Project.erp_external_id == external_id))
            if external_id
            else None
        )
        by_number = self._session.scalar(select(Project).where(Project.number == number))

        if by_external is not None and by_number is not None and by_external.id != by_number.id:
            raise ApplicationConflictError(
                "Le numéro de projet et l'identifiant ERP pointent vers deux projets locaux différents.",
                code="project_sync_identity_conflict",
                context={"erp_external_id": external_id, "project_number": number},
            )

        row = by_external or by_number
        if row is None:
            self._session.add(
                Project(
                    erp_external_id=external_id or None,
                    number=number,
                    name=name,
                    client=_optional_text(project.client),
                    project_manager_external_id=_optional_text(
                        project.project_manager_external_id
                    ),
                    project_manager_name=_optional_text(project.project_manager_name),
                    status=_text(project.status) or "active",
                )
            )
            self._session.flush()
            return "created"

        if external_id and row.erp_external_id and row.erp_external_id != external_id:
            raise ApplicationConflictError(
                "Le projet local est déjà lié à un autre identifiant ERP.",
                code="project_sync_external_id_conflict",
                context={
                    "project_number": row.number,
                    "existing_erp_external_id": row.erp_external_id,
                    "incoming_erp_external_id": external_id,
                },
            )

        values = {
            "number": number,
            "name": name,
            "client": _optional_text(project.client),
            "project_manager_external_id": _optional_text(
                project.project_manager_external_id
            ),
            "project_manager_name": _optional_text(project.project_manager_name),
            "status": _text(project.status) or "active",
        }
        if external_id:
            # Manual XLSX exports do not expose the Acumatica REST row id. In that
            # case preserve any existing binding; a later live ERP sync can attach it.
            values["erp_external_id"] = external_id

        changed = False
        for field, value in values.items():
            if getattr(row, field) != value:
                setattr(row, field, value)
                changed = True

        if changed:
            self._session.flush()
            return "updated"
        return "unchanged"
