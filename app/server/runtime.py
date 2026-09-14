from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import os

from fastapi import FastAPI
import uvicorn

from ..application.security import AuthPrincipal, ROLE_ADMIN, normalize_roles
from ..infrastructure.acumatica import AcumaticaProjectSource, AcumaticaProjectSourceSettings
from .frontend import FrontendBuildError, attach_frontend
from .http import create_api_app
from .security import static_auth_resolver


DATABASE_URL_ENV = "RESOURCEPLANNER_DATABASE_URL"
HOST_ENV = "RESOURCEPLANNER_HOST"
PORT_ENV = "RESOURCEPLANNER_PORT"
LOG_LEVEL_ENV = "RESOURCEPLANNER_LOG_LEVEL"
ACTOR_NAME_ENV = "RESOURCEPLANNER_ACTOR_NAME"
FRONTEND_DIST_ENV = "RESOURCEPLANNER_FRONTEND_DIST"
AUTH_MODE_ENV = "RESOURCEPLANNER_AUTH_MODE"
LOCAL_AUTH_NAME_ENV = "RESOURCEPLANNER_LOCAL_AUTH_NAME"
LOCAL_AUTH_EMAIL_ENV = "RESOURCEPLANNER_LOCAL_AUTH_EMAIL"
LOCAL_AUTH_ROLES_ENV = "RESOURCEPLANNER_LOCAL_AUTH_ROLES"
ALLOW_LOCAL_AUTH_NETWORK_ENV = "RESOURCEPLANNER_ALLOW_LOCAL_AUTH_NETWORK"
ACUMATICA_BASE_URL_ENV = "RESOURCEPLANNER_ACUMATICA_BASE_URL"
ACUMATICA_ACCESS_TOKEN_ENV = "RESOURCEPLANNER_ACUMATICA_ACCESS_TOKEN"
ACUMATICA_ENDPOINT_ENV = "RESOURCEPLANNER_ACUMATICA_ENDPOINT"
ACUMATICA_VERSION_ENV = "RESOURCEPLANNER_ACUMATICA_VERSION"
ACUMATICA_ENTITY_ENV = "RESOURCEPLANNER_ACUMATICA_PROJECT_ENTITY"
ACUMATICA_NUMBER_FIELD_ENV = "RESOURCEPLANNER_ACUMATICA_PROJECT_NUMBER_FIELD"
ACUMATICA_NAME_FIELD_ENV = "RESOURCEPLANNER_ACUMATICA_PROJECT_NAME_FIELD"
ACUMATICA_CLIENT_FIELD_ENV = "RESOURCEPLANNER_ACUMATICA_PROJECT_CLIENT_FIELD"
ACUMATICA_MANAGER_FIELD_ENV = "RESOURCEPLANNER_ACUMATICA_PROJECT_MANAGER_FIELD"
ACUMATICA_STATUS_FIELD_ENV = "RESOURCEPLANNER_ACUMATICA_PROJECT_STATUS_FIELD"
ACUMATICA_PAGE_SIZE_ENV = "RESOURCEPLANNER_ACUMATICA_PAGE_SIZE"

_ALLOWED_LOG_LEVELS = {"critical", "error", "warning", "info", "debug", "trace"}
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class ServerConfigurationError(RuntimeError):
    """Raised when the server environment is incomplete or invalid."""


def _text(value: object) -> str:
    return str(value or "").strip()


def _bool(value: object, *, default: bool = False) -> bool:
    text = _text(value).casefold()
    if not text:
        return default
    if text in {"1", "true", "yes", "oui", "on"}:
        return True
    if text in {"0", "false", "no", "non", "off"}:
        return False
    raise ServerConfigurationError("Une valeur booléenne attend true/false ou 1/0.")


def _port(value: object) -> int:
    text = _text(value)
    if not text:
        return 8000
    try:
        port = int(text)
    except ValueError as exc:
        raise ServerConfigurationError(
            f"{PORT_ENV} doit être un entier entre 1 et 65535."
        ) from exc
    if not 1 <= port <= 65535:
        raise ServerConfigurationError(
            f"{PORT_ENV} doit être compris entre 1 et 65535."
        )
    return port


def _acumatica_page_size(value: object) -> int:
    text = _text(value)
    if not text:
        return 200
    try:
        page_size = int(text)
    except ValueError as exc:
        raise ServerConfigurationError(
            f"{ACUMATICA_PAGE_SIZE_ENV} doit être un entier positif."
        ) from exc
    if not 1 <= page_size <= 1000:
        raise ServerConfigurationError(
            f"{ACUMATICA_PAGE_SIZE_ENV} doit être compris entre 1 et 1000."
        )
    return page_size


def _acumatica_settings(values: Mapping[str, str]) -> AcumaticaProjectSourceSettings | None:
    base_url = _text(values.get(ACUMATICA_BASE_URL_ENV))
    bearer_token = _text(values.get(ACUMATICA_ACCESS_TOKEN_ENV))
    version = _text(values.get(ACUMATICA_VERSION_ENV))

    if not any((base_url, bearer_token, version)):
        return None

    missing = [
        name
        for name, value in (
            (ACUMATICA_BASE_URL_ENV, base_url),
            (ACUMATICA_ACCESS_TOKEN_ENV, bearer_token),
            (ACUMATICA_VERSION_ENV, version),
        )
        if not value
    ]
    if missing:
        raise ServerConfigurationError(
            "Configuration Acumatica incomplète; variables requises: " + ", ".join(missing)
        )

    return AcumaticaProjectSourceSettings(
        base_url=base_url,
        bearer_token=bearer_token,
        endpoint=_text(values.get(ACUMATICA_ENDPOINT_ENV)) or "Default",
        version=version,
        entity=_text(values.get(ACUMATICA_ENTITY_ENV)) or "Project",
        number_field=_text(values.get(ACUMATICA_NUMBER_FIELD_ENV)) or "ProjectID",
        name_field=_text(values.get(ACUMATICA_NAME_FIELD_ENV)) or "Description",
        client_field=_text(values.get(ACUMATICA_CLIENT_FIELD_ENV)) or "Customer",
        project_manager_field=_text(values.get(ACUMATICA_MANAGER_FIELD_ENV)) or "ProjectManager",
        status_field=_text(values.get(ACUMATICA_STATUS_FIELD_ENV)) or "Status",
        page_size=_acumatica_page_size(values.get(ACUMATICA_PAGE_SIZE_ENV)),
    )


def _default_local_principal() -> AuthPrincipal:
    return AuthPrincipal.from_roles(
        local_user_id=None,
        issuer="urn:resourceplanner:local",
        subject="local-user",
        display_name="Administrateur local",
        email=None,
        roles=(ROLE_ADMIN,),
        auth_mode="local",
    )


def _local_principal(values: Mapping[str, str], *, actor_name: str) -> AuthPrincipal:
    roles_text = _text(values.get(LOCAL_AUTH_ROLES_ENV)) or ROLE_ADMIN
    try:
        roles = normalize_roles(tuple(part.strip() for part in roles_text.split(",") if part.strip()))
    except ValueError as exc:
        raise ServerConfigurationError(str(exc)) from exc
    if not roles:
        raise ServerConfigurationError(f"{LOCAL_AUTH_ROLES_ENV} doit contenir au moins un rôle.")
    return AuthPrincipal.from_roles(
        local_user_id=None,
        issuer="urn:resourceplanner:local",
        subject="local-user",
        display_name=_text(values.get(LOCAL_AUTH_NAME_ENV)) or actor_name or "Administrateur local",
        email=_text(values.get(LOCAL_AUTH_EMAIL_ENV)) or None,
        roles=roles,
        auth_mode="local",
    )


@dataclass(frozen=True, slots=True)
class ServerSettings:
    """Environment-driven configuration for the standalone FastAPI server."""

    database_url: str = field(repr=False)
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "info"
    actor_name: str = "api"
    frontend_dist: str | None = None
    auth_principal: AuthPrincipal = field(default_factory=_default_local_principal, repr=False)
    acumatica: AcumaticaProjectSourceSettings | None = field(default=None, repr=False)

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "ServerSettings":
        values = os.environ if environ is None else environ
        database_url = _text(values.get(DATABASE_URL_ENV))
        if not database_url:
            raise ServerConfigurationError(f"{DATABASE_URL_ENV} est requis pour démarrer le serveur.")

        host = _text(values.get(HOST_ENV)) or "127.0.0.1"
        port = _port(values.get(PORT_ENV))
        log_level = (_text(values.get(LOG_LEVEL_ENV)) or "info").casefold()
        if log_level not in _ALLOWED_LOG_LEVELS:
            allowed = ", ".join(sorted(_ALLOWED_LOG_LEVELS))
            raise ServerConfigurationError(
                f"{LOG_LEVEL_ENV} doit être l'une des valeurs suivantes: {allowed}."
            )
        actor_name = _text(values.get(ACTOR_NAME_ENV)) or "api"
        frontend_dist = _text(values.get(FRONTEND_DIST_ENV)) or None
        auth_mode = (_text(values.get(AUTH_MODE_ENV)) or "local").casefold()
        if auth_mode != "local":
            raise ServerConfigurationError(
                f"{AUTH_MODE_ENV}={auth_mode!r} n'est pas encore disponible; utiliser 'local'."
            )
        allow_network = _bool(values.get(ALLOW_LOCAL_AUTH_NETWORK_ENV), default=False)
        if host.casefold() not in _LOOPBACK_HOSTS and not allow_network:
            raise ServerConfigurationError(
                "Le mode d'authentification local ne peut pas écouter sur le réseau sans "
                f"{ALLOW_LOCAL_AUTH_NETWORK_ENV}=true."
            )
        auth_principal = _local_principal(values, actor_name=actor_name)

        return cls(
            database_url=database_url,
            host=host,
            port=port,
            log_level=log_level,
            actor_name=actor_name,
            frontend_dist=frontend_dist,
            auth_principal=auth_principal,
            acumatica=_acumatica_settings(values),
        )


def create_configured_app(settings: ServerSettings | None = None) -> FastAPI:
    """Create the configured SQL API and optionally attach the React build."""

    resolved = settings or ServerSettings.from_environment()
    project_source = (
        AcumaticaProjectSource(resolved.acumatica)
        if resolved.acumatica is not None
        else None
    )
    app = create_api_app(
        resolved.database_url,
        actor_name=resolved.actor_name,
        project_source=project_source,
        acumatica_info=(
            resolved.acumatica.safe_summary() if resolved.acumatica is not None else None
        ),
        auth_resolver=static_auth_resolver(resolved.auth_principal),
    )
    if resolved.frontend_dist is not None:
        try:
            attach_frontend(app, resolved.frontend_dist, required=True)
        except FrontendBuildError as exc:
            raise ServerConfigurationError(str(exc)) from exc
    return app


def run_server(settings: ServerSettings | None = None) -> None:
    """Run one Uvicorn process using the explicit server configuration."""

    resolved = settings or ServerSettings.from_environment()
    app = create_configured_app(resolved)
    uvicorn.run(
        app,
        host=resolved.host,
        port=resolved.port,
        log_level=resolved.log_level,
        reload=False,
    )


def main() -> None:
    try:
        run_server()
    except ServerConfigurationError as exc:
        raise SystemExit(f"Configuration serveur invalide: {exc}")
