from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import os

import uvicorn

from .http import create_api_app


DATABASE_URL_ENV = "RESOURCEPLANNER_DATABASE_URL"
HOST_ENV = "RESOURCEPLANNER_HOST"
PORT_ENV = "RESOURCEPLANNER_PORT"
LOG_LEVEL_ENV = "RESOURCEPLANNER_LOG_LEVEL"
ACTOR_NAME_ENV = "RESOURCEPLANNER_ACTOR_NAME"

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


@dataclass(frozen=True, slots=True)
class ServerSettings:
    """Environment-driven configuration for the standalone FastAPI server."""

    database_url: str = field(repr=False)
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "info"
    actor_name: str = "api"

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
        )


def create_configured_app(settings: ServerSettings | None = None):
    """Create the API app without running migrations or opening an Excel runtime."""

    resolved = settings or ServerSettings.from_environment()
    return create_api_app(
        resolved.database_url,
        actor_name=resolved.actor_name,
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
    run_server()
