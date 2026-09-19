from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...application.security import AuthPrincipal
from .base import utc_now
from .identity_models import AppUser, AuthLoginTransaction, AuthSession
from .identity_repository import SqlUserIdentityRepository


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class LoginTransactionRecord:
    nonce: str
    code_verifier: str


class SqlAuthSessionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_login_transaction(
        self,
        *,
        state: str,
        nonce: str,
        code_verifier: str,
        browser_binding: str,
        expires_at: datetime,
    ) -> None:
        self._session.add(
            AuthLoginTransaction(
                state_hash=_hash(state),
                nonce=nonce,
                code_verifier=code_verifier,
                browser_binding_hash=_hash(browser_binding),
                expires_at=expires_at,
            )
        )
        self._session.flush()

    def consume_login_transaction(
        self,
        state: str,
        *,
        browser_binding: str,
        now: datetime | None = None,
    ) -> LoginTransactionRecord | None:
        row = self._session.scalar(
            select(AuthLoginTransaction).where(
                AuthLoginTransaction.state_hash == _hash(state),
                AuthLoginTransaction.consumed_at.is_(None),
            )
        )
        current = _aware(now or utc_now())
        if row is None or _aware(row.expires_at) <= current:
            return None
        expected_binding = str(row.browser_binding_hash or "")
        if not expected_binding or not secrets.compare_digest(
            expected_binding,
            _hash(browser_binding),
        ):
            return None
        row.consumed_at = current
        self._session.flush()
        return LoginTransactionRecord(nonce=row.nonce, code_verifier=row.code_verifier)

    def create_session(
        self,
        *,
        raw_token: str,
        csrf_token: str | None = None,
        user_id: str,
        expires_at: datetime,
    ) -> None:
        self._session.add(
            AuthSession(
                token_hash=_hash(raw_token),
                csrf_token_hash=_hash(csrf_token) if csrf_token else None,
                user_id=user_id,
                expires_at=expires_at,
            )
        )
        self._session.flush()

    def resolve_principal(
        self,
        raw_token: str,
        *,
        now: datetime | None = None,
        auth_mode: str = "oidc",
    ) -> AuthPrincipal | None:
        row = self._session.scalar(
            select(AuthSession).where(
                AuthSession.token_hash == _hash(raw_token),
                AuthSession.revoked_at.is_(None),
            )
        )
        current = _aware(now or utc_now())
        if row is None or _aware(row.expires_at) <= current:
            return None
        user = self._session.get(AppUser, row.user_id)
        if user is None or not user.active:
            return None
        record = SqlUserIdentityRepository._record(user)
        return AuthPrincipal.from_roles(
            local_user_id=record.user_id,
            issuer=record.issuer,
            subject=record.subject,
            display_name=record.display_name,
            email=record.email,
            employee_external_id=record.employee_external_id,
            roles=record.roles,
            auth_mode=auth_mode,
        )


    def validate_csrf(
        self,
        raw_token: str,
        csrf_token: str,
        *,
        now: datetime | None = None,
    ) -> bool:
        row = self._session.scalar(
            select(AuthSession).where(
                AuthSession.token_hash == _hash(raw_token),
                AuthSession.revoked_at.is_(None),
            )
        )
        current = _aware(now or utc_now())
        if row is None or _aware(row.expires_at) <= current:
            return False
        expected = str(row.csrf_token_hash or "")
        return bool(expected) and secrets.compare_digest(expected, _hash(csrf_token))

    def revoke_session(self, raw_token: str, *, now: datetime | None = None) -> bool:
        row = self._session.scalar(
            select(AuthSession).where(
                AuthSession.token_hash == _hash(raw_token),
                AuthSession.revoked_at.is_(None),
            )
        )
        if row is None:
            return False
        row.revoked_at = _aware(now or utc_now())
        self._session.flush()
        return True
