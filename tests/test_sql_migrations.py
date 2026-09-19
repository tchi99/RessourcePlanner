from __future__ import annotations

from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.infrastructure.sql import Base


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations"
INITIAL_REVISION = MIGRATIONS / "versions" / "0001_initial_planning_schema.py"
EXPECTED_TABLES = {
    "command_idempotency_receipts",
    "projects",
    "request_lines",
    "request_line_competencies",
    "resource_requirement_competencies",
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

    def test_migration_matches_orm_columns_and_nullability(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "schema-parity.db"
            config = alembic_config(database_path)
            command.upgrade(config, "head")

            engine = create_engine(f"sqlite:///{database_path.as_posix()}")
            inspector = inspect(engine)
            try:
                for table_name, table in Base.metadata.tables.items():
                    migrated_columns = {
                        column["name"]: bool(column["nullable"])
                        for column in inspector.get_columns(table_name)
                    }
                    model_columns = {
                        column.name: bool(column.nullable)
                        for column in table.columns
                    }
                    self.assertEqual(
                        migrated_columns,
                        model_columns,
                        f"Migration/ORM drift for {table_name}",
                    )
            finally:
                engine.dispose()

    def test_initial_migration_compiles_offline_for_postgresql_and_mssql(self) -> None:
        for url in ("postgresql://", "mssql+pyodbc://"):
            output = StringIO()
            command.upgrade(offline_config(url, output), "head", sql=True)
            ddl = output.getvalue().upper()

            self.assertIn("CREATE TABLE PROJECTS", ddl, url)
            self.assertIn("CREATE TABLE RESOURCE_REQUIREMENTS", ddl, url)
            self.assertIn("CREATE TABLE SHIFTS", ddl, url)
            self.assertIn("CREATE TABLE WORKFORCE_REQUEST_PERIODS", ddl, url)
            self.assertIn("CREATE TABLE WORKFORCE_REQUEST_PERIOD_SELECTIONS", ddl, url)
            self.assertIn("CREATE TABLE WORKFORCE_REQUEST_PERIOD_REQUIREMENTS", ddl, url)
            self.assertIn("CREATE TABLE COMMAND_IDEMPOTENCY_RECEIPTS", ddl, url)
            self.assertIn("UQ_COMMAND_IDEMPOTENCY_ACTOR_SCOPE_KEY", ddl, url)
            self.assertIn("WORKFORCE_REQUEST_ID", ddl, url)
            self.assertIn("CREATE TABLE REQUEST_LINES", ddl, url)
            self.assertIn("CREATE TABLE REQUEST_LINE_COMPETENCIES", ddl, url)
            self.assertIn("CREATE TABLE RESOURCE_REQUIREMENT_COMPETENCIES", ddl, url)
            self.assertIn("SOURCE_REQUEST_LINE_ID", ddl, url)
            self.assertIn("REQUEST_LINE_ID", ddl, url)
            self.assertIn("AGGREGATE_VERSION", ddl, url)
            self.assertIn("LINE_MODE", ddl, url)
            self.assertIn("ESTIMATED_HOURS_SOURCE", ddl, url)
            self.assertIn("DEFAULT_HOURS_PER_DAY", ddl, url)

    def test_request_line_migration_backfills_without_rebuilding_plan(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "request-line-backfill.db"
            config = alembic_config(database_path)
            command.upgrade(config, "0021_auth_security")
            engine = create_engine(f"sqlite:///{database_path.as_posix()}")

            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "INSERT INTO projects (id, number, name) VALUES ('P1', 'P-1', 'Projet')"
                )
                connection.exec_driver_sql(
                    "INSERT INTO resources (id, name, resource_class) "
                    "VALUES ('R1', 'Alice', 'AUT')"
                )
                connection.exec_driver_sql(
                    "INSERT INTO work_packages (id, project_id, code, name) "
                    "VALUES ('WP1', 'P1', 'WP-1', 'Lot 1')"
                )
                connection.exec_driver_sql(
                    "INSERT INTO task_catalog_items "
                    "(id, project_number, task_code, label) "
                    "VALUES ('TASK1', 'P-1', 'T-1', 'Tâche ERP')"
                )
                connection.exec_driver_sql(
                    "INSERT INTO competencies (id, name, active, sort_order) "
                    "VALUES ('C1', 'PLC', 1, 0)"
                )
                connection.exec_driver_sql(
                    """
                    INSERT INTO workforce_requests (
                        id, legacy_demand_number, project_id, work_package_id,
                        erp_task_code, erp_task_label, confirmation,
                        desired_start, desired_end, description, resource_count,
                        required_competencies, estimated_hours, estimated_days,
                        proposed_resource_id, status
                    ) VALUES (
                        'D1', 'DEM-1', 'P1', 'WP1',
                        'T-1', 'Tâche ERP', 'Confirmée',
                        '2026-09-21', '2026-09-25', 'Besoin historique', 2,
                        'PLC', 48, 3, 'R1', 'En planification'
                    )
                    """
                )
                connection.exec_driver_sql(
                    "INSERT INTO workforce_request_competencies "
                    "(workforce_request_id, competency_id) VALUES ('D1', 'C1')"
                )
                connection.exec_driver_sql(
                    """
                    INSERT INTO workforce_request_periods (
                        id, period_key, workforce_request_id, sequence, kind,
                        alternative_group, start_date, end_date, hours,
                        confirmation, proposed_resource_id, resource_count,
                        desired_active_days, active, created_at, updated_at
                    ) VALUES (
                        'PER1', 'PER-1', 'D1', 0, 'CUMULATIVE',
                        NULL, '2026-09-21', '2026-09-23', 32,
                        'Confirmée', 'R1', 2, 2, 1,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                )
                connection.exec_driver_sql(
                    """
                    INSERT INTO workforce_request_periods (
                        id, period_key, workforce_request_id, sequence, kind,
                        alternative_group, start_date, end_date, hours,
                        confirmation, resource_count, active, created_at, updated_at
                    ) VALUES (
                        'ALT1', 'ALT-1', 'D1', 1, 'ALTERNATIVE',
                        'VISITE', '2026-09-24', '2026-09-24', 8,
                        'Tentative', 1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                )
                connection.exec_driver_sql(
                    """
                    INSERT INTO workforce_request_period_selections (
                        workforce_request_id, alternative_group, period_id,
                        selected_at, selected_by_name
                    ) VALUES (
                        'D1', 'VISITE', 'ALT1', CURRENT_TIMESTAMP, 'Coord'
                    )
                    """
                )
                connection.exec_driver_sql(
                    """
                    INSERT INTO resource_requirements (
                        id, legacy_segment_id, project_id, workforce_request_id,
                        assigned_resource_id, start_date, end_date, planned_hours,
                        status, required_competency_id, planning_type, priority,
                        origin
                    ) VALUES (
                        'REQ1', 'SEG-1', 'P1', 'D1',
                        'R1', '2026-09-21', '2026-09-25', 24,
                        'Planifié', 'C1', 'Flexible', 'Normale', 'REQUEST'
                    )
                    """
                )
                connection.exec_driver_sql(
                    """
                    INSERT INTO resource_requirements (
                        id, legacy_segment_id, project_id, workforce_request_id,
                        start_date, end_date, planned_hours, status,
                        planning_type, priority, origin
                    ) VALUES (
                        'REQ2', 'SEG-2', 'P1', 'D1',
                        '2026-09-21', '2026-09-25', 24, 'À assigner',
                        'Flexible', 'Normale', 'REQUEST'
                    )
                    """
                )
                connection.exec_driver_sql(
                    """
                    INSERT INTO resource_requirements (
                        id, legacy_segment_id, project_id, workforce_request_id,
                        start_date, end_date, planned_hours, status,
                        required_competency_id, planning_type, priority, origin
                    ) VALUES (
                        'AD1', 'SEG-AD', 'P1', NULL,
                        '2026-09-21', '2026-09-21', 4, 'À assigner',
                        'C1', 'Flexible', 'Normale', 'AD_HOC'
                    )
                    """
                )
                connection.exec_driver_sql(
                    "INSERT INTO workforce_request_period_requirements "
                    "(resource_requirement_id, period_id) VALUES ('REQ1', 'PER1')"
                )
                connection.exec_driver_sql(
                    "INSERT INTO shifts "
                    "(id, legacy_allocation_id, resource_requirement_id, resource_id, "
                    "work_date, hours, allocation_type, source, locked) "
                    "VALUES ('SHIFT1', 'AUTO-1', 'REQ1', 'R1', "
                    "'2026-09-21', 8, 'Flexible', 'AUTO', 1)"
                )
            engine.dispose()

            command.upgrade(config, "head")
            engine = create_engine(f"sqlite:///{database_path.as_posix()}")
            with engine.connect() as connection:
                line = connection.exec_driver_sql(
                    """
                    SELECT id, workforce_request_id, position, kind, slot_count,
                           required_resource_class, required_competencies_snapshot,
                           desired_start, desired_end, desired_active_days,
                           estimated_hours, estimated_hours_source,
                           default_hours_per_day, confirmation, work_package_id,
                           task_catalog_item_id, erp_task_code, erp_task_label,
                           proposed_resource_id, description, active
                    FROM request_lines
                    WHERE id = 'D1'
                    """
                ).mappings().one()
                self.assertEqual(line["workforce_request_id"], "D1")
                self.assertEqual(line["position"], 0)
                self.assertEqual(line["kind"], "WORKFORCE")
                self.assertEqual(line["slot_count"], 2)
                self.assertIsNone(line["required_resource_class"])
                self.assertEqual(line["required_competencies_snapshot"], "PLC")
                self.assertEqual(float(line["desired_active_days"]), 3.0)
                self.assertEqual(float(line["estimated_hours"]), 48.0)
                self.assertEqual(line["estimated_hours_source"], "LEGACY")
                self.assertIsNone(line["default_hours_per_day"])
                self.assertEqual(line["work_package_id"], "WP1")
                self.assertEqual(line["task_catalog_item_id"], "TASK1")
                self.assertEqual(line["erp_task_code"], "T-1")
                self.assertEqual(line["erp_task_label"], "Tâche ERP")
                self.assertEqual(line["proposed_resource_id"], "R1")
                self.assertEqual(line["description"], "Besoin historique")
                self.assertEqual(line["active"], 1)

                line_competencies = connection.exec_driver_sql(
                    "SELECT request_line_id, competency_id "
                    "FROM request_line_competencies"
                ).fetchall()
                self.assertEqual(line_competencies, [("D1", "C1")])

                period_lines = connection.exec_driver_sql(
                    "SELECT id, request_line_id FROM workforce_request_periods "
                    "ORDER BY id"
                ).fetchall()
                self.assertEqual(period_lines, [("ALT1", "D1"), ("PER1", "D1")])
                selection_line = connection.exec_driver_sql(
                    "SELECT request_line_id FROM workforce_request_period_selections "
                    "WHERE workforce_request_id = 'D1' AND alternative_group = 'VISITE'"
                ).scalar_one()
                self.assertEqual(selection_line, "D1")

                requirement_lines = connection.exec_driver_sql(
                    "SELECT id, source_request_line_id FROM resource_requirements "
                    "ORDER BY id"
                ).fetchall()
                self.assertEqual(
                    requirement_lines,
                    [("AD1", None), ("REQ1", "D1"), ("REQ2", "D1")],
                )
                requirement_competencies = connection.exec_driver_sql(
                    "SELECT resource_requirement_id, competency_id "
                    "FROM resource_requirement_competencies "
                    "ORDER BY resource_requirement_id, competency_id"
                ).fetchall()
                self.assertEqual(
                    requirement_competencies,
                    [("AD1", "C1"), ("REQ1", "C1"), ("REQ2", "C1")],
                )

                version_row = connection.exec_driver_sql(
                    "SELECT aggregate_version, line_mode "
                    "FROM workforce_requests WHERE id = 'D1'"
                ).one()
                self.assertEqual(version_row[0], 1)
                self.assertEqual(version_row[1], 0)
                self.assertEqual(
                    connection.exec_driver_sql(
                        "SELECT COUNT(*) FROM resource_requirements"
                    ).scalar_one(),
                    3,
                )
                shift = connection.exec_driver_sql(
                    "SELECT id, resource_requirement_id, hours, locked "
                    "FROM shifts WHERE id = 'SHIFT1'"
                ).one()
                self.assertEqual(shift[0], "SHIFT1")
                self.assertEqual(shift[1], "REQ1")
                self.assertEqual(float(shift[2]), 8.0)
                self.assertEqual(shift[3], 1)
            engine.dispose()

            command.downgrade(config, "0021_auth_security")
            engine = create_engine(f"sqlite:///{database_path.as_posix()}")
            inspector = inspect(engine)
            self.assertNotIn("request_lines", inspector.get_table_names())
            with engine.connect() as connection:
                self.assertEqual(
                    connection.exec_driver_sql(
                        "SELECT COUNT(*) FROM workforce_requests"
                    ).scalar_one(),
                    1,
                )
                self.assertEqual(
                    connection.exec_driver_sql(
                        "SELECT COUNT(*) FROM resource_requirements"
                    ).scalar_one(),
                    3,
                )
                self.assertEqual(
                    connection.exec_driver_sql(
                        "SELECT COUNT(*) FROM shifts"
                    ).scalar_one(),
                    1,
                )
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
