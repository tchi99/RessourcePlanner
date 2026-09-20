from __future__ import annotations

import unittest

from sqlalchemy import select

from app.application.task_catalog import TaskCatalogItem, TaskCatalogSyncService
from app.infrastructure.sql import (
    Base,
    BusinessContact,
    TaskCatalogEntry,
    create_session_factory,
    create_sql_engine,
)
from app.infrastructure.sql.task_catalog_repository import SqlTaskCatalogRepository


class StubTaskSource:
    def __init__(self, rows: list[TaskCatalogItem]) -> None:
        self.rows = rows

    def list_tasks(self) -> tuple[TaskCatalogItem, ...]:
        return tuple(self.rows)


class TaskCatalogSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_sql_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.factory = create_session_factory(self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()

    def _sync(self, rows: list[TaskCatalogItem]):
        with self.factory.begin() as session:
            return TaskCatalogSyncService(
                StubTaskSource(rows),
                SqlTaskCatalogRepository(session),
            ).synchronize()

    def test_sync_is_idempotent_and_explicit_status_deactivates(self) -> None:
        item = TaskCatalogItem(
            project_number="P-1",
            code="210",
            label="Automatisation",
            status="Actif",
            active=True,
            time_entry_enabled=True,
        )
        first = self._sync([item])
        self.assertEqual(
            (first.created, first.updated, first.unchanged, first.deactivated),
            (1, 0, 0, 0),
        )

        second = self._sync([item])
        self.assertEqual(
            (second.created, second.updated, second.unchanged, second.deactivated),
            (0, 0, 1, 0),
        )

        changed = TaskCatalogItem(
            project_number="P-1",
            code="210",
            label="Automatisation mise à jour",
            status="Actif",
            active=True,
            time_entry_enabled=True,
        )
        third = self._sync([changed])
        self.assertEqual(
            (third.created, third.updated, third.unchanged, third.deactivated),
            (0, 1, 0, 0),
        )

        inactive = TaskCatalogItem(
            project_number="P-1",
            code="210",
            label="Automatisation mise à jour",
            status="Inactif",
            active=False,
            time_entry_enabled=True,
        )
        fourth = self._sync([inactive])
        self.assertEqual(
            (fourth.created, fourth.updated, fourth.unchanged, fourth.deactivated),
            (0, 0, 0, 1),
        )

        with self.factory() as session:
            repository = SqlTaskCatalogRepository(session)
            self.assertEqual(repository.search(project_number="P-1"), ())
            rows = repository.search(project_number="P-1", active_only=False)
            self.assertEqual(len(rows), 1)
            self.assertFalse(rows[0].active)
            self.assertEqual(rows[0].label, "Automatisation mise à jour")

    def test_sync_preserves_locally_owned_task_contact_links(self) -> None:
        item = TaskCatalogItem(
            project_number="P-LOCAL",
            code="210",
            label="Tâche initiale",
            active=True,
        )
        self._sync([item])

        with self.factory.begin() as session:
            session.add_all(
                [
                    BusinessContact(
                        id="BC-RESP",
                        display_name="Responsable local",
                        phone="555-0500",
                    ),
                    BusinessContact(
                        id="BC-COORD",
                        display_name="Coordonnateur local",
                        phone="555-0501",
                    ),
                ]
            )
            session.flush()
            row = session.scalar(
                select(TaskCatalogEntry).where(
                    TaskCatalogEntry.project_number == "P-LOCAL",
                    TaskCatalogEntry.task_code == "210",
                )
            )
            assert row is not None
            row.operational_responsible_contact_id = "BC-RESP"
            row.coordinator_contact_id = "BC-COORD"

        changed = TaskCatalogItem(
            project_number="P-LOCAL",
            code="210",
            label="Tâche ERP mise à jour",
            status="Actif",
            active=True,
        )
        self._sync([changed])

        with self.factory() as session:
            row = session.scalar(
                select(TaskCatalogEntry).where(
                    TaskCatalogEntry.project_number == "P-LOCAL",
                    TaskCatalogEntry.task_code == "210",
                )
            )
            assert row is not None
            self.assertEqual(row.operational_responsible_contact_id, "BC-RESP")
            self.assertEqual(row.coordinator_contact_id, "BC-COORD")
            projected = SqlTaskCatalogRepository(session).search(
                project_number="P-LOCAL"
            )[0]
            self.assertEqual(projected.id, row.id)
            self.assertEqual(
                projected.operational_responsible_contact_id,
                "BC-RESP",
            )
            self.assertEqual(projected.coordinator_contact_id, "BC-COORD")

    def test_same_task_code_is_valid_for_different_projects(self) -> None:
        result = self._sync(
            [
                TaskCatalogItem("P-1", "210", "Service", active=True),
                TaskCatalogItem("P-2", "210", "Achats automatisation", active=True),
            ]
        )
        self.assertEqual(result.created, 2)

        with self.factory() as session:
            repository = SqlTaskCatalogRepository(session)
            p1 = repository.search(project_number="P-1", query="210")
            p2 = repository.search(project_number="P-2", query="achats")
        self.assertEqual(p1[0].label, "Service")
        self.assertEqual(p2[0].label, "Achats automatisation")


if __name__ == "__main__":
    unittest.main()
