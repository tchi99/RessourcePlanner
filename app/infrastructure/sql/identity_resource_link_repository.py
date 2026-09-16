from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...application.identity_resource_link import IdentityResourceLinkRepositoryPort
from ...application.security import UserIdentityRecord
from .identity_models import AppUser
from .identity_repository import SqlUserIdentityRepository
from .models import Resource


class SqlIdentityResourceLinkRepository(IdentityResourceLinkRepositoryPort):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_user_by_id(self, user_id: str) -> UserIdentityRecord | None:
        row = self._session.get(AppUser, str(user_id).strip())
        return SqlUserIdentityRepository._record(row) if row is not None else None

    def get_user_by_employee_external_id(
        self,
        employee_external_id: str,
    ) -> UserIdentityRecord | None:
        external_id = str(employee_external_id or "").strip()
        if not external_id:
            return None
        row = self._session.scalar(
            select(AppUser).where(AppUser.employee_external_id == external_id)
        )
        return SqlUserIdentityRepository._record(row) if row is not None else None

    def resource_exists_by_external_id(self, employee_external_id: str) -> bool:
        external_id = str(employee_external_id or "").strip()
        if not external_id:
            return False
        return self._session.scalar(
            select(Resource.id).where(Resource.external_id == external_id)
        ) is not None

    def set_employee_external_id(
        self,
        user_id: str,
        employee_external_id: str | None,
    ) -> UserIdentityRecord:
        row = self._session.get(AppUser, str(user_id).strip())
        if row is None:
            raise KeyError(f"Utilisateur {user_id} introuvable")
        value = str(employee_external_id or "").strip() or None
        row.employee_external_id = value
        self._session.flush()
        return SqlUserIdentityRepository._record(row)
