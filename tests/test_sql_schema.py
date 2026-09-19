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
    "app_users",
    "auth_login_transactions",
    "auth_sessions",
    "command_idempotency_receipts",
    "communication_batches",
    "communication_contacts",
    "communication_messages",
    "communication_snapshot_lines",
    "competencies",
    "planning_change_history",
    "projects",
    "request_lines",
    "request_line_competencies",
    "resource_requirement_competencies",
    "resources",
    "work_packages",
    "workforce_requests",
    "workforce_request_competencies",
    "workforce_request_history",
    "workforce_request_periods",
    "workforce_request_period_selections",
    "workforce_request_period_requirements",
    "resource_availability_rules",
    "resource_competencies",
    "resource_requirements",
    "shifts",
    "task_catalog_items",
}


class SqlSchemaTests(unittest.TestCase):
    def test_expected_core_tables_and_nullability_contracts(self) -> None:
        self.assertEqual(set(Base.metadata.tables), EXPECTED_TABLES)

        requirements = Base.metadata.tables["resource_requirements"].c
        requests = Base.metadata.tables["workforce_requests"].c
        periods = Base.metadata.tables["workforce_request_periods"].c
        period_requirements = Base.metadata.tables["workforce_request_period_requirements"].c
        availability = Base.metadata.tables["resource_availability_rules"].c
        idempotency = Base.metadata.tables["command_idempotency_receipts"].c
        users = Base.metadata.tables["app_users"].c
        login_transactions = Base.metadata.tables["auth_login_transactions"].c
        auth_sessions = Base.metadata.tables["auth_sessions"].c
        communication_contacts = Base.metadata.tables["communication_contacts"].c
        communication_batches = Base.metadata.tables["communication_batches"].c
        communication_messages = Base.metadata.tables["communication_messages"].c
        communication_snapshots = Base.metadata.tables["communication_snapshot_lines"].c
        planning_history = Base.metadata.tables["planning_change_history"].c
        task_catalog = Base.metadata.tables["task_catalog_items"].c
        competencies = Base.metadata.tables["competencies"].c
        resource_competencies = Base.metadata.tables["resource_competencies"].c
        request_competencies = Base.metadata.tables["workforce_request_competencies"].c
        request_lines = Base.metadata.tables["request_lines"].c
        line_competencies = Base.metadata.tables["request_line_competencies"].c
        requirement_competencies = Base.metadata.tables[
            "resource_requirement_competencies"
        ].c
        selections = Base.metadata.tables["workforce_request_period_selections"].c

        self.assertFalse(requirements.project_id.nullable)
        self.assertTrue(requirements.workforce_request_id.nullable)
        self.assertTrue(requirements.source_request_line_id.nullable)
        self.assertTrue(requests.work_package_id.nullable)
        self.assertTrue(requests.erp_task_code.nullable)
        self.assertTrue(requests.erp_task_label.nullable)
        self.assertFalse(requests.project_id.nullable)
        self.assertFalse(requests.aggregate_version.nullable)
        self.assertFalse(periods.workforce_request_id.nullable)
        self.assertTrue(periods.request_line_id.nullable)
        self.assertTrue(selections.request_line_id.nullable)
        self.assertFalse(periods.start_date.nullable)
        self.assertFalse(periods.end_date.nullable)
        self.assertFalse(period_requirements.resource_requirement_id.nullable)
        self.assertFalse(period_requirements.period_id.nullable)
        self.assertTrue(availability.resource_id.nullable)
        self.assertFalse(idempotency.actor_name.nullable)
        self.assertFalse(idempotency.command_scope.nullable)
        self.assertFalse(idempotency.idempotency_key.nullable)
        self.assertFalse(idempotency.request_fingerprint.nullable)
        self.assertFalse(idempotency.response_json.nullable)
        self.assertFalse(users.issuer.nullable)
        self.assertFalse(users.subject.nullable)
        self.assertFalse(users.display_name.nullable)
        self.assertTrue(users.email.nullable)
        self.assertFalse(users.roles_json.nullable)
        self.assertFalse(users.active.nullable)
        self.assertFalse(login_transactions.state_hash.nullable)
        self.assertFalse(login_transactions.nonce.nullable)
        self.assertFalse(login_transactions.code_verifier.nullable)
        self.assertFalse(login_transactions.expires_at.nullable)
        self.assertTrue(login_transactions.consumed_at.nullable)
        self.assertFalse(auth_sessions.token_hash.nullable)
        self.assertFalse(auth_sessions.user_id.nullable)
        self.assertFalse(auth_sessions.expires_at.nullable)
        self.assertTrue(auth_sessions.revoked_at.nullable)
        self.assertFalse(communication_contacts.recipient_id.nullable)
        self.assertTrue(communication_contacts.email.nullable)
        self.assertFalse(communication_batches.snapshot_fingerprint.nullable)
        self.assertFalse(communication_batches.status.nullable)
        self.assertFalse(communication_messages.batch_id.nullable)
        self.assertFalse(communication_messages.included.nullable)
        self.assertFalse(communication_snapshots.batch_id.nullable)
        self.assertFalse(communication_snapshots.resource_id.nullable)
        self.assertFalse(planning_history.entity_type.nullable)
        self.assertFalse(planning_history.entity_id.nullable)
        self.assertFalse(planning_history.entity_reference.nullable)
        self.assertFalse(planning_history.action.nullable)
        self.assertTrue(planning_history.parent_reference.nullable)
        self.assertTrue(planning_history.details.nullable)
        self.assertTrue(planning_history.actor_name.nullable)
        self.assertFalse(planning_history.occurred_at.nullable)
        self.assertFalse(task_catalog.project_number.nullable)
        self.assertFalse(task_catalog.task_code.nullable)
        self.assertFalse(task_catalog.label.nullable)
        self.assertFalse(task_catalog.status.nullable)
        self.assertFalse(task_catalog.active.nullable)
        self.assertFalse(competencies.name.nullable)
        self.assertFalse(competencies.active.nullable)
        self.assertFalse(competencies.sort_order.nullable)
        self.assertFalse(resource_competencies.resource_id.nullable)
        self.assertFalse(resource_competencies.competency_id.nullable)
        self.assertFalse(request_competencies.workforce_request_id.nullable)
        self.assertFalse(request_competencies.competency_id.nullable)
        self.assertFalse(request_lines.workforce_request_id.nullable)
        self.assertFalse(request_lines.position.nullable)
        self.assertFalse(request_lines.kind.nullable)
        self.assertFalse(request_lines.slot_count.nullable)
        self.assertTrue(request_lines.required_resource_class.nullable)
        self.assertTrue(request_lines.required_competencies_snapshot.nullable)
        self.assertTrue(request_lines.desired_active_days.nullable)
        self.assertTrue(request_lines.estimated_hours.nullable)
        self.assertTrue(request_lines.estimated_hours_source.nullable)
        self.assertTrue(request_lines.default_hours_per_day.nullable)
        self.assertFalse(request_lines.confirmation.nullable)
        self.assertFalse(request_lines.active.nullable)
        self.assertFalse(line_competencies.request_line_id.nullable)
        self.assertFalse(line_competencies.competency_id.nullable)
        self.assertFalse(requirement_competencies.resource_requirement_id.nullable)
        self.assertFalse(requirement_competencies.competency_id.nullable)
        self.assertTrue(requirements.required_competency_id.nullable)

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

    def test_idempotency_key_is_unique_per_actor_and_command_scope(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        receipts = Base.metadata.tables["command_idempotency_receipts"]
        base = {
            "id": "I1",
            "actor_name": "Jean",
            "command_scope": "demand.create",
            "idempotency_key": "same-key",
            "request_fingerprint": "a" * 64,
            "response_json": "{}",
        }
        with engine.begin() as connection:
            connection.execute(receipts.insert().values(**base))
            connection.execute(
                receipts.insert().values(
                    **{**base, "id": "I2", "command_scope": "segment.create"}
                )
            )
            connection.execute(
                receipts.insert().values(
                    **{**base, "id": "I3", "actor_name": "Other"}
                )
            )

        with self.assertRaises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(receipts.insert().values(**{**base, "id": "I4"}))

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
