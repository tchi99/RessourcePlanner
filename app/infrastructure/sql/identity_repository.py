from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...application.security import UserIdentityRecord, normalize_roles
from .identity_models import AppUser


class SqlUserIdentityRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _record(row: AppUser) -> UserIdentityRecord:
        raw_roles = json.loads(row.roles_json or "[]")
        roles = normalize_roles(tuple(str(role) for role in raw_roles))
        return UserIdentityRecord(
            user_id=row.id,
            issuer=row.issuer,
            subject=row.subject,
            display_name=row.display_name,
            email=row.email,
            roles=roles,
            active=bool(row.active),
        )

    def list_users(self) -> tuple[UserIdentityRecord, ...]:
        rows = self._session.scalars(
            select(AppUser).order_by(AppUser.display_name, AppUser.issuer, AppUser.subject)
        ).all()
        return tuple(self._record(row) for row in rows)

    def get_by_id(self, user_id: str) -> UserIdentityRecord | None:
        row = self._session.get(AppUser, str(user_id).strip())
        return self._record(row) if row is not None else None

    def get_by_external_identity(self, issuer: str, subject: str) -> UserIdentityRecord | None:
        row = self._session.scalar(
            select(AppUser).where(
                AppUser.issuer == str(issuer).strip(),
                AppUser.subject == str(subject).strip(),
            )
        )
        return self._record(row) if row is not None else None

    def upsert(
        self,
        *,
        issuer: str,
        subject: str,
        display_name: str,
        email: str | None,
        roles: tuple[str, ...] | list[str] | set[str],
        active: bool = True,
    ) -> UserIdentityRecord:
        issuer_value = str(issuer).strip()
        subject_value = str(subject).strip()
        display_name_value = str(display_name).strip()
        if not issuer_value or not subject_value or not display_name_value:
            raise ValueError("issuer, subject et display_name sont requis")
        normalized_roles = normalize_roles(roles)
        if not normalized_roles:
            raise ValueError("Au moins un rôle RessourcePlanner est requis")

        row = self._session.scalar(
            select(AppUser).where(
                AppUser.issuer == issuer_value,
                AppUser.subject == subject_value,
            )
        )
        if row is None:
            row = AppUser(
                issuer=issuer_value,
                subject=subject_value,
                display_name=display_name_value,
                email=str(email).strip() if email else None,
                roles_json=json.dumps(list(normalized_roles), separators=(",", ":")),
                active=bool(active),
            )
            self._session.add(row)
        else:
            row.display_name = display_name_value
            row.email = str(email).strip() if email else None
            row.roles_json = json.dumps(list(normalized_roles), separators=(",", ":"))
            row.active = bool(active)
        self._session.flush()
        return self._record(row)
