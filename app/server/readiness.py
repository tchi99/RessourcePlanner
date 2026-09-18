from __future__ import annotations

from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import DBAPIError


ROOT = Path(__file__).resolve().parents[2]


class DatabaseReadinessError(RuntimeError):
    """Safe runtime-readiness failure without leaking connection details."""

    def __init__(self, code: str, message: str) -> None:
        self.code = str(code)
        self.message = str(message)
        super().__init__(self.message)


def expected_alembic_head() -> str:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    heads = ScriptDirectory.from_config(config).get_heads()
    if len(heads) != 1:
        raise DatabaseReadinessError(
            "migration_heads_invalid",
            "Le dépôt doit exposer une seule tête Alembic.",
        )
    return heads[0]


def check_database_readiness(engine: Engine) -> dict[str, Any]:
    """Check connectivity and exact schema revision without mutating business data."""

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1")).scalar_one()
            tables = set(inspect(connection).get_table_names())
            if "alembic_version" not in tables:
                raise DatabaseReadinessError(
                    "migration_missing",
                    "La base n'a pas encore été initialisée par Alembic.",
                )

            try:
                revisions = tuple(
                    str(value)
                    for value in connection.execute(
                        text("SELECT version_num FROM alembic_version")
                    ).scalars()
                )
            except DBAPIError as exc:
                raise DatabaseReadinessError(
                    "migration_unreadable",
                    "La version Alembic de la base ne peut pas être lue.",
                ) from exc
    except DatabaseReadinessError:
        raise
    except DBAPIError as exc:
        raise DatabaseReadinessError(
            "database_unavailable",
            "La base de données n'est pas joignable ou interrogeable.",
        ) from exc

    expected = expected_alembic_head()
    if revisions != (expected,):
        raise DatabaseReadinessError(
            "migration_required",
            "La base de données n'est pas sur la révision Alembic attendue.",
        )

    return {
        "status": "ok",
        "dialect": engine.dialect.name,
        "alembic_revision": expected,
    }
