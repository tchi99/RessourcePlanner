from __future__ import annotations

import unittest

from sqlalchemy import select

from app.application.project_sync import ExternalProjectRecord, ProjectSyncService
from app.infrastructure.sql import Base, Project, create_session_factory, create_sql_engine, transactional_session
from app.infrastructure.sql.project_sync_repository import SqlProjectSyncRepository


class StubProjectSource:
    def __init__(self, rows: list[ExternalProjectRecord]) -> None:
        self.rows = rows

    def list_projects(self) -> tuple[ExternalProjectRecord, ...]:
        return tuple(self.rows)


class ManualProjectExportSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_sql_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.factory = create_session_factory(self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()

    def _sync(self, rows: list[ExternalProjectRecord]):
        with transactional_session(self.factory) as session:
            return ProjectSyncService(
                StubProjectSource(rows),
                SqlProjectSyncRepository(session),
            ).synchronize()

    def test_manual_export_leaves_erp_id_free_then_live_sync_adopts_project(self) -> None:
        manual = ExternalProjectRecord(
            external_id=None,
            number="P-250",
            name="Projet importé",
            client="Client A",
            project_manager_name="Gestionnaire A",
            status="Actif",
        )
        first = self._sync([manual])
        self.assertEqual((first.created, first.updated, first.unchanged), (1, 0, 0))

        with self.factory() as session:
            row = session.scalar(select(Project).where(Project.number == "P-250"))
            assert row is not None
            self.assertIsNone(row.erp_external_id)

        live = ExternalProjectRecord(
            external_id="ERP-ROW-250",
            number="P-250",
            name="Projet importé",
            client="Client A",
            project_manager_name="Gestionnaire A",
            status="Actif",
        )
        second = self._sync([live])
        self.assertEqual((second.created, second.updated, second.unchanged), (0, 1, 0))

        with self.factory() as session:
            row = session.scalar(select(Project).where(Project.number == "P-250"))
            assert row is not None
            self.assertEqual(row.erp_external_id, "ERP-ROW-250")

    def test_manual_export_preserves_existing_live_erp_binding(self) -> None:
        self._sync(
            [
                ExternalProjectRecord(
                    external_id="ERP-ROW-300",
                    number="P-300",
                    name="Projet live",
                    status="Actif",
                )
            ]
        )
        result = self._sync(
            [
                ExternalProjectRecord(
                    external_id=None,
                    number="P-300",
                    name="Projet renommé dans export",
                    status="Actif",
                )
            ]
        )
        self.assertEqual((result.created, result.updated, result.unchanged), (0, 1, 0))

        with self.factory() as session:
            row = session.scalar(select(Project).where(Project.number == "P-300"))
            assert row is not None
            self.assertEqual(row.erp_external_id, "ERP-ROW-300")
            self.assertEqual(row.name, "Projet renommé dans export")


if __name__ == "__main__":
    unittest.main()
