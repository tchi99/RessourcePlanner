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
                    # ERP discovery never authorizes a resource locally.
                    active=False,
                    erp_status=_optional_text(employee.erp_status),
                    erp_active=bool(employee.erp_active),
                    erp_department_description=_optional_text(employee.department_description),
                    erp_department_code=_optional_text(employee.department_code),
                    erp_employee_class=_optional_text(employee.employee_class),
                    erp_supervisor_external_id=_optional_text(employee.supervisor_external_id),
                    erp_phone=_optional_text(employee.telephone),
                    erp_branch_code=_optional_text(employee.branch_code),
                    erp_contact_id=employee.contact_id,
                )
            )
            self._session.flush()
            return "created"

        # ERP owns only these organizational fields. Local activation (active),
        # resource class, competencies, note, sort order and availability stay local
        # to RessourcePlanner and are never overwritten by synchronization.
        values = {
            "name": display_name,
            "email": _optional_text(employee.email),
            "erp_status": _optional_text(employee.erp_status),
            "erp_active": bool(employee.erp_active),
            "erp_department_description": _optional_text(employee.department_description),
            "erp_department_code": _optional_text(employee.department_code),
            "erp_employee_class": _optional_text(employee.employee_class),
            "erp_supervisor_external_id": _optional_text(employee.supervisor_external_id),
            "erp_phone": _optional_text(employee.telephone),
            "erp_branch_code": _optional_text(employee.branch_code),
            "erp_contact_id": employee.contact_id,
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
