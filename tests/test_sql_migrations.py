from __future__ import annotations

from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations"
INITIAL_REVISION = MIGRATIONS / "versions" / "0001_initial_planning_schema.py"
EXPECTED_TABLES = {
    "projects",
    "resources",
    "work_packages",
    "workforce_requests",
    "workforce_request_history",
    "resource_availability_rules",
    "resource_requirements",
    "shifts",
}


def alembic_config(database_path: Path) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(MIGRATIONS))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


def offline_config(url: str, output: StringIO) -> Config:
    config = Config(str(ROOT / "alembic.ini"), output_buffer=output)
    config.set_main_option("script_location", str(MIGRATIONS))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


class SqlMigrationTests(unittest.TestCase):
    def test_initial_revision_is_self_contained(self) -> None:
        source = INITIAL_REVISION.read_text(encoding="utf-8")

        self.assertIn('revision: str = "0001_initial_planning_schema"', source)
        self.assertIn("down_revision", source)
        self.assertNotIn("app.infrastructure.sql", source)
        self.assertNotIn("from app", source)
        self.assertNotIn("import app", source)

    def test_upgrade_and_downgrade_on_sqlite(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "migration-test.db"
            config = alembic_config(database_path)

            command.upgrade(config, "head")
            engine = create_engine(f"sqlite:///{database_path.as_posix()}")
            upgraded = set(inspect(engine).get_table_names())
            self.assertTrue(EXPECTED_TABLES.issubset(upgraded))
            self.assertIn("alembic_version", upgraded)
            engine.dispose()

            command.downgrade(config, "base")
            engine = create_engine(f"sqlite:///{database_path.as_posix()}")
            downgraded = set(inspect(engine).get_table_names())
            self.assertFalse(EXPECTED_TABLES.intersection(downgraded))
            engine.dispose()

    def test_initial_migration_compiles_offline_for_postgresql_and_mssql(self) -> None:
        for url in ("postgresql://", "mssql+pyodbc://"):
            output = StringIO()
            command.upgrade(offline_config(url, output), "head", sql=True)
            ddl = output.getvalue().upper()

            self.assertIn("CREATE TABLE PROJECTS", ddl, url)
            self.assertIn("CREATE TABLE RESOURCE_REQUIREMENTS", ddl, url)
            self.assertIn("CREATE TABLE SHIFTS", ddl, url)
            self.assertIn("WORKFORCE_REQUEST_ID", ddl, url)


if __name__ == "__main__":
    unittest.main()
