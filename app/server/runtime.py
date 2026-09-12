from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import os

from fastapi import FastAPI
import uvicorn

from ..infrastructure.acumatica import AcumaticaProjectSource, AcumaticaProjectSourceSettings
from .http import create_api_app


DATABASE_URL_ENV = "RESOURCEPLANNER_DATABASE_URL"
HOST_ENV = "RESOURCEPLANNER_HOST"
PORT_ENV = "RESOURCEPLANNER_PORT"
LOG_LEVEL_ENV = "RESOURCEPLANNER_LOG_LEVEL"
ACTOR_NAME_ENV = "RESOURCEPLANNER_ACTOR_NAME"
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


class ServerConfigurationError(RuntimeError):
    """Raised when the server environment is incomplete or invalid."""


def _text(value: object) -> str:
    return str(value or "").strip()


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


def _acumatica_settings(
    values: Mapping[str, str],
) -> AcumaticaProjectSourceSettings | None:
    base_url = _text(values.get(ACUMATICA_BASE_URL_ENV))
    access_token = _text(values.get(ACUMATICA_ACCESS_TOKEN_ENV))
    version = _text(values.get(ACUMATICA_VERSION_ENV))

    if not any((base_url, access_token, version)):
        return None

    missing = [
        name
        for name, value in (
            (ACUMATICA_BASE_URL_ENV, base_url),
            (ACUMATICA_ACCESS_TOKEN_ENV, access_token),
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
        access_token=access_token,
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


@dataclass(frozen=True, slots=True)
class ServerSettings:
    """Environment-driven configuration for the standalone FastAPI server."""

    database_url: str = field(repr=False)
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "info"
    actor_name: str = "api"
    acumatica: AcumaticaProjectSourceSettings | None = field(default=None, repr=False)

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> "ServerSettings":
        values = os.environ if environ is None else environ
        database_url = _text(values.get(DATABASE_URL_ENV))
        if not database_url:
            raise ServerConfigurationError(
                f"{DATABASE_URL_ENV} est requis pour démarrer le serveur."
            )

        host = _text(values.get(HOST_ENV)) or "127.0.0.1"
        port = _port(values.get(PORT_ENV))
        log_level = (_text(values.get(LOG_LEVEL_ENV)) or "info").casefold()
        if log_level not in _ALLOWED_LOG_LEVELS:
            allowed = ", ".join(sorted(_ALLOWED_LOG_LEVELS))
            raise ServerConfigurationError(
                f"{LOG_LEVEL_ENV} doit être l'une des valeurs suivantes: {allowed}."
            )
        actor_name = _text(values.get(ACTOR_NAME_ENV)) or "api"

        return cls(
            database_url=database_url,
            host=host,
            port=port,
            log_level=log_level,
            actor_name=actor_name,
            acumatica=_acumatica_settings(values),
        )


def create_configured_app(settings: ServerSettings | None = None) -> FastAPI:
    """Create the API app without running migrations or opening an Excel runtime."""

    resolved = settings or ServerSettings.from_environment()
    project_source = (
        AcumaticaProjectSource(resolved.acumatica)
        if resolved.acumatica is not None
        else None
    )
    return create_api_app(
        resolved.database_url,
        actor_name=resolved.actor_name,
        project_source=project_source,
        acumatica_info=(
            resolved.acumatica.safe_summary()
            if resolved.acumatica is not None
            else None
        ),
    )


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
