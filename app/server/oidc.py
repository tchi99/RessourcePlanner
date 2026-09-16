from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import secrets
from typing import Any

from fastapi import Request

from ..application.security import AuthPrincipal
from ..infrastructure.acumatica.oidc import OidcClient
from ..infrastructure.sql import SqlAuthSessionRepository, SqlSessionFactory
from ..infrastructure.sql.base import utc_now
from .security import AuthResolver


@dataclass(frozen=True, slots=True)
class OidcRuntime:
    client: OidcClient
    cookie_name: str = "resourceplanner_session"
    session_hours: int = 8
    secure_cookie: bool = True
    cookie_samesite: str = "lax"

    @property
    def login_ttl(self) -> timedelta:
        return timedelta(minutes=10)

    @property
    def session_ttl(self) -> timedelta:
        return timedelta(hours=self.session_hours)

    def new_secret(self, length: int = 48) -> str:
        return secrets.token_urlsafe(length)


def oidc_session_auth_resolver(cookie_name: str) -> AuthResolver:
    def resolve(request: Request) -> AuthPrincipal | None:
        raw_token = str(request.cookies.get(cookie_name) or "").strip()
        if not raw_token:
            return None
        factory: SqlSessionFactory = request.app.state.session_factory
        with factory() as session:
            return SqlAuthSessionRepository(session).resolve_principal(raw_token)

    return resolve


def create_login_transaction(
    factory: SqlSessionFactory,
    runtime: OidcRuntime,
) -> tuple[str, str, str]:
    state = runtime.new_secret()
    nonce = runtime.new_secret()
    code_verifier = runtime.new_secret(64)
    with factory.begin() as session:
        SqlAuthSessionRepository(session).create_login_transaction(
            state=state,
            nonce=nonce,
            code_verifier=code_verifier,
            expires_at=utc_now() + runtime.login_ttl,
        )
    return state, nonce, code_verifier


def consume_login_transaction(
    factory: SqlSessionFactory,
    state: str,
) -> Any:
    with factory.begin() as session:
        return SqlAuthSessionRepository(session).consume_login_transaction(state)


def create_server_session(
    factory: SqlSessionFactory,
    runtime: OidcRuntime,
    *,
    user_id: str,
) -> str:
    raw_token = runtime.new_secret(64)
    with factory.begin() as session:
        SqlAuthSessionRepository(session).create_session(
            raw_token=raw_token,
            user_id=user_id,
            expires_at=utc_now() + runtime.session_ttl,
        )
    return raw_token


def revoke_server_session(
    factory: SqlSessionFactory,
    *,
    cookie_name: str,
    request: Request,
) -> None:
    raw_token = str(request.cookies.get(cookie_name) or "").strip()
    if not raw_token:
        return
    with factory.begin() as session:
        SqlAuthSessionRepository(session).revoke_session(raw_token)
