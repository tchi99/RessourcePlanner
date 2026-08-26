from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from app.server.runtime import (
    ServerConfigurationError,
    ServerSettings,
    create_configured_app,
)


class ServerReadinessError(RuntimeError):
    """Raised when a read-only server smoke check fails."""


def _response_json(response, *, path: str) -> Any:
    if response.status_code != 200:
        body = response.text.strip()
        if len(body) > 500:
            body = body[:500] + "..."
        raise ServerReadinessError(
            f"{path} a retourné HTTP {response.status_code}: {body or '<réponse vide>'}"
        )
    try:
        return response.json()
    except ValueError as exc:
        raise ServerReadinessError(f"{path} n'a pas retourné du JSON valide.") from exc


def check_server_runtime(settings: ServerSettings) -> dict[str, Any]:
    """Exercise the configured API without mutating business data."""

    app = create_configured_app(settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        health = _response_json(client.get("/health"), path="/health")
        projects = _response_json(
            client.get("/api/v1/projects?active_only=true"),
            path="/api/v1/projects",
        )
        resources = _response_json(
            client.get("/api/v1/resources"),
            path="/api/v1/resources",
        )
        openapi = _response_json(client.get("/openapi.json"), path="/openapi.json")

    if not isinstance(health, dict) or health.get("status") != "ok":
        raise ServerReadinessError("/health n'a pas confirmé status=ok.")
    if not isinstance(projects, list):
        raise ServerReadinessError("/api/v1/projects n'a pas retourné une liste.")
    if not isinstance(resources, list):
        raise ServerReadinessError("/api/v1/resources n'a pas retourné une liste.")
    if not isinstance(openapi, dict) or not openapi.get("paths"):
        raise ServerReadinessError("/openapi.json ne contient aucune route.")

    return {
        "status": "ok",
        "database": str(health.get("database") or "unknown"),
        "api": str(health.get("api") or "unknown"),
        "active_projects": len(projects),
        "active_resources": len(resources),
        "openapi_paths": len(openapi.get("paths", {})),
    }


def _print_error(status: str, message: str, **extra: str) -> None:
    payload = {"status": status, "message": message, **extra}
    print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)


def main() -> int:
    try:
        settings = ServerSettings.from_environment()
    except ServerConfigurationError as exc:
        _print_error("configuration_error", str(exc))
        return 2

    try:
        summary = check_server_runtime(settings)
    except ServerReadinessError as exc:
        _print_error("readiness_error", str(exc))
        return 3
    except Exception as exc:
        # A missing DBAPI/ODBC driver or another infrastructure error can occur before
        # FastAPI is able to translate it to its stable HTTP contract. Report only the
        # exception type here so a connection string/password can never leak to output.
        _print_error(
            "technical_error",
            "Le préflight n'a pas pu initialiser ou interroger le backend.",
            error_type=type(exc).__name__,
        )
        return 4

    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
