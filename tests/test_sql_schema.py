from __future__ import annotations

import ast
from datetime import date
from pathlib import Path
import unittest

from sqlalchemy import create_engine, inspect
from sqlalchemy.dialects import mssql, postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateIndex, CreateTable

from app.infrastructure.sql import Base


ROOT = Path(__file__).resolve().parents[1]
APPLICATION = ROOT / "app" / "application"
DOMAIN_ENGINE = ROOT / "app" / "domain" / "planning_engine.py"
DAY = date(2026, 8, 26)

EXPECTED_TABLES = {
    "projects",
    "resources",
    "work_packages",
    "workforce_requests",
    "workforce_request_history",
    "workforce_request_periods",
    "workforce_request_period_selections",
    "workforce_request_period_requirements",
    "resource_availability_rules",
    "resource_requirements",
    "shifts",
}


class SqlSchemaTests(unittest.TestCase):
    def test_expected_core_tables_and_nullability_contracts(self) -> None:
        self.assertEqual(set(Base.metadata.tables), EXPECTED_TABLES)

        requirements = Base.metadata.tables["resource_requirements"].c
        requests = Base.metadata.tables["workforce_requests"].c
        periods = Base.metadata.tables["workforce_request_periods"].c
        period_requirements = Base.metadata.tables["workforce_request_period_requirements"].c
        availability = Base.metadata.tables["resource_availability_rules"].c

        self.assertFalse(requirements.project_id.nullable)
        self.assertTrue(requirements.workforce_request_id.nullable)
        self.assertTrue(requests.work_package_id.nullable)
        self.assertFalse(requests.project_id.nullable)
        self.assertFalse(periods.workforce_request_id.nullable)
        self.assertFalse(periods.start_date.nullable)
        self.assertFalse(periods.end_date.nullable)
        self.assertFalse(period_requirements.resource_requirement_id.nullable)
        self.assertFalse(period_requirements.period_id.nullable)
        self.assertTrue(availability.resource_id.nullable)

    def test_metadata_creates_all_tables_on_sqlite_memory(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)

        self.assertEqual(set(inspect(engine).get_table_names()), EXPECTED_TABLES)

    def test_quick_shift_without_request_is_valid_but_request_origin_without_request_is_not(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        projects = Base.metadata.tables["projects"]
        resources = Base.metadata.tables["resources"]
        requirements = Base.metadata.tables["resource_requirements"]
        shifts = Base.metadata.tables["shifts"]

        with engine.begin() as connection:
            connection.execute(
                projects.insert().values(id="P1", number="P-1", name="Projet test")
            )
            connection.execute(resources.insert().values(id="R1", name="Alice"))
            connection.execute(
                requirements.insert().values(
                    id="REQ-QS",
                    project_id="P1",
                    workforce_request_id=None,
                    assigned_resource_id="R1",
                    start_date=DAY,
                    end_date=DAY,
                    planned_hours=4,
                    origin="QUICK_SHIFT",
                )
            )
            connection.execute(
                shifts.insert().values(
                    id="SHIFT-QS",
                    resource_requirement_id="REQ-QS",
                    resource_id="R1",
                    work_date=DAY,
                    hours=4,
                    source="MANUAL",
                    locked=True,
                )
            )

        with self.assertRaises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    requirements.insert().values(
                        id="REQ-INVALID",
                        project_id="P1",
                        workforce_request_id=None,
                        start_date=DAY,
                        end_date=DAY,
                        planned_hours=2,
                        origin="REQUEST",
                    )
                )

    def test_only_holiday_rule_may_be_global(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        availability = Base.metadata.tables["resource_availability_rules"]

        with engine.begin() as connection:
            connection.execute(
                availability.insert().values(
                    id="HOLIDAY",
                    resource_id=None,
                    availability_type="Jour férié",
                    start_date=DAY,
                    end_date=DAY,
                )
            )

        with self.assertRaises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    availability.insert().values(
                        id="VACATION-GLOBAL",
                        resource_id=None,
                        availability_type="Vacances",
                        start_date=DAY,
                        end_date=DAY,
                    )
                )

    def test_schema_and_indexes_compile_for_supported_dialects(self) -> None:
        dialects = {
            "sqlite": sqlite.dialect(),
            "postgresql": postgresql.dialect(),
            "mssql": mssql.dialect(),
        }

        for dialect_name, dialect in dialects.items():
            for table in Base.metadata.sorted_tables:
                ddl = str(CreateTable(table).compile(dialect=dialect))
                self.assertIn("CREATE TABLE", ddl.upper(), dialect_name)
                for index in table.indexes:
                    index_ddl = str(CreateIndex(index).compile(dialect=dialect))
                    self.assertIn("CREATE", index_ddl.upper(), dialect_name)
                    self.assertIn("INDEX", index_ddl.upper(), dialect_name)

    def test_application_and_pure_engine_do_not_depend_on_sqlalchemy(self) -> None:
        files = [*APPLICATION.rglob("*.py"), DOMAIN_ENGINE]
        for path in files:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imports: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.append(node.module or "")
            self.assertFalse(
                any(module == "sqlalchemy" or module.startswith("sqlalchemy.") for module in imports),
                f"SQLAlchemy leaked into portable core: {path.relative_to(ROOT)}",
            )


if __name__ == "__main__":
    unittest.main()
