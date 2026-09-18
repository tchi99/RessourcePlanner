from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError, NoSuchModuleError


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from app.infrastructure.sql import create_sql_engine
from app.server.runtime import (
    ServerConfigurationError,
    ServerSettings,
    create_configured_app,
)


class ServerReadinessError(RuntimeError):
    """Raised when the configured API is reachable but not ready."""


class DriverReadinessError(RuntimeError):
    """Raised when the configured SQLAlchemy/DBAPI driver cannot be loaded."""


class ConnectivityReadinessError(RuntimeError):
    """Raised when the database driver loads but the server cannot be reached/used."""


class MigrationReadinessError(RuntimeError):
    """Raised when the target database is not on the expected Alembic head."""


def _expected_alembic_head() -> str:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    heads = ScriptDirectory.from_config(config).get_heads()
    if len(heads) != 1:
        raise MigrationReadinessError(
            "Le dépôt doit exposer une seule tête Alembic avant le démarrage."
        )
    return heads[0]


def check_database_preflight(database_url: str) -> dict[str, Any]:
    """Validate driver, connectivity and migration state without changing data."""

    try:
        engine = create_sql_engine(database_url)
    except (ModuleNotFoundError, ImportError, NoSuchModuleError) as exc:
        raise DriverReadinessError(
            "Le dialecte/driver de base de données configuré n'est pas installé."
        ) from exc

    try:
        try:
            connection = engine.connect()
        except (ModuleNotFoundError, ImportError, NoSuchModuleError) as exc:
            raise DriverReadinessError(
                "Le DBAPI/driver ODBC configuré n'est pas installé."
            ) from exc
        except DBAPIError as exc:
            raise ConnectivityReadinessError(
                "Le driver est chargé, mais la connexion à la base de données a échoué."
            ) from exc

        with connection:
            try:
                connection.execute(text("SELECT 1")).scalar_one()
                tables = set(inspect(connection).get_table_names())
            except DBAPIError as exc:
                raise ConnectivityReadinessError(
                    "La connexion a été ouverte, mais la base n'est pas interrogeable."
                ) from exc

            if "alembic_version" not in tables:
                raise MigrationReadinessError(
                    "La table alembic_version est absente; exécuter les migrations avant le serveur."
                )

            try:
                revisions = tuple(
                    str(value)
                    for value in connection.execute(
                        text("SELECT version_num FROM alembic_version")
                    ).scalars()
                )
            except DBAPIError as exc:
                raise MigrationReadinessError(
                    "Impossible de lire la version Alembic de la base."
                ) from exc

            expected = _expected_alembic_head()
            if revisions != (expected,):
                current = ", ".join(revisions) if revisions else "<aucune>"
                raise MigrationReadinessError(
                    f"Migration requise: base={current}; dépôt={expected}."
                )
            return {
                "database": engine.dialect.name,
                "alembic_revision": expected,
                "connectivity": "ok",
            }
    finally:
        engine.dispose()


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

    database = check_database_preflight(settings.database_url)
    try:
        app = create_configured_app(settings)
    except (ModuleNotFoundError, ImportError, NoSuchModuleError) as exc:
        raise DriverReadinessError(
            "Le driver de base de données requis par le serveur n'est pas installé."
        ) from exc
    except DBAPIError as exc:
        raise ConnectivityReadinessError(
            "Le serveur n'a pas pu ouvrir sa connexion de base de données."
        ) from exc

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
        "database": str(health.get("database") or database["database"]),
        "api": str(health.get("api") or "unknown"),
        "alembic_revision": database["alembic_revision"],
        "connectivity": database["connectivity"],
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
    except DriverReadinessError as exc:
        _print_error("driver_error", str(exc))
        return 3
    except ConnectivityReadinessError as exc:
        _print_error("connectivity_error", str(exc))
        return 4
    except MigrationReadinessError as exc:
        _print_error("migration_error", str(exc))
        return 5
    except ServerReadinessError as exc:
        _print_error("readiness_error", str(exc))
        return 6
    except Exception as exc:
        # Never echo the exception message: it may contain a URL, host, username or
        # connection-string fragment. The type is sufficient for unexpected failures.
        _print_error(
            "technical_error",
            "Le préflight a rencontré une erreur technique non classée.",
            error_type=type(exc).__name__,
        )
        return 7

    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
