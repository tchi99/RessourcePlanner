from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...application.employee_sync import ExternalEmployeeRecord, EmployeeSyncRepositoryPort
from ...application.errors import ApplicationConflictError, ApplicationValidationError
from .models import Resource


def _text(value: object) -> str:
    return str(value or "").strip()


def _optional_text(value: object) -> str | None:
    text = _text(value)
    return text or None


class SqlEmployeeSyncRepository(EmployeeSyncRepositoryPort):
    """Idempotent ERP employee upsert preserving planning-owned resource attributes."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_external_employee(self, employee: ExternalEmployeeRecord) -> str:
        external_id = _text(employee.external_id)
        display_name = _text(employee.display_name)
        if not external_id:
            raise ApplicationValidationError(
                "Un identifiant externe est requis pour synchroniser une ressource.",
                code="employee_sync_external_id_required",
            )
        if not display_name:
            raise ApplicationValidationError(
                "Un nom est requis pour synchroniser une ressource.",
                code="employee_sync_name_required",
                context={"external_id": external_id},
            )

        row = self._session.scalar(
            select(Resource).where(Resource.external_id == external_id)
        )
        if row is None:
            # Never adopt a manually-created resource by name: names are not stable
            # identities. Fail closed so an administrator can link the external ID
            # explicitly instead of creating an accidental duplicate.
            candidates = self._session.scalars(
                select(Resource).where(Resource.external_id.is_(None))
            ).all()
            unlinked_name_match = next(
                (
                    candidate
                    for candidate in candidates
                    if _text(candidate.name).casefold() == display_name.casefold()
                ),
                None,
            )
            if unlinked_name_match is not None:
                raise ApplicationConflictError(
                    "Une ressource locale non liée porte déjà ce nom; son identifiant externe doit être confirmé explicitement.",
                    code="employee_sync_unlinked_name_conflict",
                    context={
                        "external_id": external_id,
                        "resource_id": unlinked_name_match.id,
                    },
                )
            self._session.add(
                Resource(
                    external_id=external_id,
                    name=display_name,
                    email=_optional_text(employee.email),
                    active=bool(employee.active),
                )
            )
            self._session.flush()
            return "created"

        # ERP owns only these organizational fields. Resource class, competencies,
        # note, sort order and availability stay local to RessourcePlanner.
        values = {
            "name": display_name,
            "email": _optional_text(employee.email),
            "active": bool(employee.active),
        }
        changed = False
        for field, value in values.items():
            if getattr(row, field) != value:
                setattr(row, field, value)
                changed = True
        if changed:
            self._session.flush()
            return "updated"
        return "unchanged"
