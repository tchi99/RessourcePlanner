from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import os

from fastapi import FastAPI
import uvicorn

from ..application.security import AuthPrincipal, ROLE_ADMIN, normalize_roles
from ..infrastructure.acumatica import AcumaticaProjectSource, AcumaticaProjectSourceSettings
from ..infrastructure.acumatica.oidc import OidcClient, OidcClientSettings
from .frontend import FrontendBuildError, attach_frontend
from .http import create_api_app
from .oidc import OidcRuntime, oidc_session_auth_resolver
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
OIDC_DISCOVERY_URL_ENV = "RESOURCEPLANNER_OIDC_DISCOVERY_URL"
OIDC_CLIENT_ID_ENV = "RESOURCEPLANNER_OIDC_CLIENT_ID"
OIDC_CLIENT_SECRET_ENV = "RESOURCEPLANNER_OIDC_CLIENT_SECRET"
OIDC_REDIRECT_URI_ENV = "RESOURCEPLANNER_OIDC_REDIRECT_URI"
OIDC_SCOPES_ENV = "RESOURCEPLANNER_OIDC_SCOPES"
OIDC_COOKIE_NAME_ENV = "RESOURCEPLANNER_OIDC_COOKIE_NAME"
OIDC_SESSION_HOURS_ENV = "RESOURCEPLANNER_OIDC_SESSION_HOURS"
OIDC_SECURE_COOKIE_ENV = "RESOURCEPLANNER_OIDC_SECURE_COOKIE"
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


def _positive_int(value: object, *, default: int, label: str, maximum: int) -> int:
    text = _text(value)
    if not text:
        return default
    try:
        parsed = int(text)
    except ValueError as exc:
        raise ServerConfigurationError(f"{label} doit être un entier positif.") from exc
    if not 1 <= parsed <= maximum:
        raise ServerConfigurationError(f"{label} doit être compris entre 1 et {maximum}.")
    return parsed


def _port(value: object) -> int:
    return _positive_int(value, default=8000, label=PORT_ENV, maximum=65535)


def _acumatica_page_size(value: object) -> int:
    return _positive_int(value, default=200, label=ACUMATICA_PAGE_SIZE_ENV, maximum=1000)


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


def _oidc_settings(values: Mapping[str, str]) -> OidcClientSettings:
    discovery_url = _text(values.get(OIDC_DISCOVERY_URL_ENV))
    client_id = _text(values.get(OIDC_CLIENT_ID_ENV))
    redirect_uri = _text(values.get(OIDC_REDIRECT_URI_ENV))
    missing = [
        name
        for name, value in (
            (OIDC_DISCOVERY_URL_ENV, discovery_url),
            (OIDC_CLIENT_ID_ENV, client_id),
            (OIDC_REDIRECT_URI_ENV, redirect_uri),
        )
        if not value
    ]
    if missing:
        raise ServerConfigurationError(
            "Configuration OIDC incomplète; variables requises: " + ", ".join(missing)
        )
    scopes = tuple(
        part for part in _text(values.get(OIDC_SCOPES_ENV) or "openid profile email").split() if part
    )
    if "openid" not in scopes:
        raise ServerConfigurationError(f"{OIDC_SCOPES_ENV} doit contenir le scope 'openid'.")
    return OidcClientSettings(
        discovery_url=discovery_url,
        client_id=client_id,
        client_secret=_text(values.get(OIDC_CLIENT_SECRET_ENV)) or None,
        redirect_uri=redirect_uri,
        scopes=scopes,
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
    auth_mode: str = "local"
    auth_principal: AuthPrincipal | None = field(default_factory=_default_local_principal, repr=False)
    oidc: OidcClientSettings | None = field(default=None, repr=False)
    oidc_cookie_name: str = "resourceplanner_session"
    oidc_session_hours: int = 8
    oidc_secure_cookie: bool = True
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
        if auth_mode not in {"local", "oidc"}:
            raise ServerConfigurationError(
                f"{AUTH_MODE_ENV} doit être 'local' ou 'oidc'."
            )

        auth_principal: AuthPrincipal | None = None
        oidc: OidcClientSettings | None = None
        oidc_cookie_name = _text(values.get(OIDC_COOKIE_NAME_ENV)) or "resourceplanner_session"
        oidc_session_hours = _positive_int(
            values.get(OIDC_SESSION_HOURS_ENV),
            default=8,
            label=OIDC_SESSION_HOURS_ENV,
            maximum=168,
        )
        oidc_secure_cookie = True

        if auth_mode == "local":
            allow_network = _bool(values.get(ALLOW_LOCAL_AUTH_NETWORK_ENV), default=False)
            if host.casefold() not in _LOOPBACK_HOSTS and not allow_network:
                raise ServerConfigurationError(
                    "Le mode d'authentification local ne peut pas écouter sur le réseau sans "
                    f"{ALLOW_LOCAL_AUTH_NETWORK_ENV}=true."
                )
            auth_principal = _local_principal(values, actor_name=actor_name)
        else:
            oidc = _oidc_settings(values)
            oidc_secure_cookie = _bool(
                values.get(OIDC_SECURE_COOKIE_ENV),
                default=oidc.redirect_uri.casefold().startswith("https://"),
            )

        return cls(
            database_url=database_url,
            host=host,
            port=port,
            log_level=log_level,
            actor_name=actor_name,
            frontend_dist=frontend_dist,
            auth_mode=auth_mode,
            auth_principal=auth_principal,
            oidc=oidc,
            oidc_cookie_name=oidc_cookie_name,
            oidc_session_hours=oidc_session_hours,
            oidc_secure_cookie=oidc_secure_cookie,
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
    oidc_runtime = None
    if resolved.auth_mode == "oidc":
        if resolved.oidc is None:
            raise ServerConfigurationError("La configuration OIDC est absente.")
        oidc_runtime = OidcRuntime(
            client=OidcClient(resolved.oidc),
            cookie_name=resolved.oidc_cookie_name,
            session_hours=resolved.oidc_session_hours,
            secure_cookie=resolved.oidc_secure_cookie,
        )
        auth_resolver = oidc_session_auth_resolver(resolved.oidc_cookie_name)
    else:
        auth_resolver = static_auth_resolver(resolved.auth_principal)

    app = create_api_app(
        resolved.database_url,
        actor_name=resolved.actor_name,
        project_source=project_source,
        acumatica_info=(
            resolved.acumatica.safe_summary() if resolved.acumatica is not None else None
        ),
        auth_resolver=auth_resolver,
        oidc_runtime=oidc_runtime,
    )
    app.state.auth_mode = resolved.auth_mode
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
