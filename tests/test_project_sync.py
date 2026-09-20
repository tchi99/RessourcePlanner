from __future__ import annotations

import unittest

from sqlalchemy import select

from app.application.errors import ApplicationConflictError
from app.application.project_sync import ExternalProjectRecord, ProjectSyncService
from app.infrastructure.sql import (
    Base,
    BusinessContact,
    Project,
    create_session_factory,
    create_sql_engine,
    transactional_session,
)
from app.infrastructure.sql.project_sync_repository import SqlProjectSyncRepository


class StubProjectSource:
    def __init__(self, rows: list[ExternalProjectRecord]) -> None:
        self.rows = rows

    def list_projects(self) -> tuple[ExternalProjectRecord, ...]:
        return tuple(self.rows)


class ProjectSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_sql_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.factory = create_session_factory(self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()

    def _sync(self, source: StubProjectSource):
        with transactional_session(self.factory) as session:
            return ProjectSyncService(
                source,
                SqlProjectSyncRepository(session),
            ).synchronize()

    def test_sync_is_idempotent_and_updates_erp_fields(self) -> None:
        source = StubProjectSource(
            [
                ExternalProjectRecord(
                    external_id="ERP-1",
                    number="P-100",
                    name="Projet initial",
                    client="Client A",
                    project_manager_external_id="USR-1",
                    project_manager_name="Alice",
                    status="Active",
                )
            ]
        )

        first = self._sync(source)
        second = self._sync(source)
        self.assertEqual((first.created, first.updated, first.unchanged), (1, 0, 0))
        self.assertEqual((second.created, second.updated, second.unchanged), (0, 0, 1))

        source.rows[0] = ExternalProjectRecord(
            external_id="ERP-1",
            number="P-100",
            name="Projet renommé",
            client="Client B",
            project_manager_external_id="USR-2",
            project_manager_name="Bob",
            status="Completed",
        )
        third = self._sync(source)
        self.assertEqual((third.created, third.updated, third.unchanged), (0, 1, 0))

        with self.factory() as session:
            row = session.scalar(select(Project).where(Project.number == "P-100"))
            assert row is not None
            self.assertEqual(row.erp_external_id, "ERP-1")
            self.assertEqual(row.name, "Projet renommé")
            self.assertEqual(row.client, "Client B")
            self.assertEqual(row.project_manager_name, "Bob")
            self.assertEqual(row.status, "Completed")

    def test_legacy_project_is_adopted_by_number_without_duplication(self) -> None:
        with transactional_session(self.factory) as session:
            session.add(
                Project(
                    id="LOCAL-1",
                    number="P-200",
                    name="Projet local historique",
                    status="Actif",
                )
            )

        result = self._sync(
            StubProjectSource(
                [
                    ExternalProjectRecord(
                        external_id="ERP-200",
                        number="P-200",
                        name="Projet ERP",
                        client="Client ERP",
                    )
                ]
            )
        )
        self.assertEqual(result.updated, 1)

        with self.factory() as session:
            rows = session.scalars(select(Project)).all()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].id, "LOCAL-1")
            self.assertEqual(rows[0].erp_external_id, "ERP-200")
            self.assertEqual(rows[0].name, "Projet ERP")

    def test_existing_external_identity_is_never_reassigned_silently(self) -> None:
        with transactional_session(self.factory) as session:
            session.add(
                Project(
                    id="LOCAL-2",
                    erp_external_id="ERP-OLD",
                    number="P-300",
                    name="Projet lié",
                    status="Actif",
                )
            )

        with self.assertRaises(ApplicationConflictError) as raised:
            self._sync(
                StubProjectSource(
                    [
                        ExternalProjectRecord(
                            external_id="ERP-NEW",
                            number="P-300",
                            name="Projet entrant",
                        )
                    ]
                )
            )
        self.assertEqual(raised.exception.code, "project_sync_external_id_conflict")

    def test_incomplete_import_preserves_local_project_contact_and_existing_manager_identity(self) -> None:
        with transactional_session(self.factory) as session:
            session.add(
                BusinessContact(
                    id="BC-PM",
                    display_name="Chargé local",
                    phone="555-0300",
                )
            )
            session.flush()
            session.add(
                Project(
                    id="P-LOCAL",
                    erp_external_id="ERP-PM",
                    number="P-PM",
                    name="Projet PM",
                    project_manager_external_id="EMP-PM",
                    project_manager_name="Chargé existant",
                    project_manager_contact_id="BC-PM",
                    status="Active",
                )
            )

        result = self._sync(
            StubProjectSource(
                [
                    ExternalProjectRecord(
                        external_id="ERP-PM",
                        number="P-PM",
                        name="Projet PM renommé",
                        client="Client",
                        project_manager_external_id=None,
                        project_manager_name=None,
                        status="Active",
                    )
                ]
            )
        )
        self.assertEqual(result.updated, 1)

        with self.factory() as session:
            row = session.get(Project, "P-LOCAL")
            assert row is not None
            self.assertEqual(row.project_manager_external_id, "EMP-PM")
            self.assertEqual(row.project_manager_name, "Chargé existant")
            self.assertEqual(row.project_manager_contact_id, "BC-PM")

    def test_missing_project_is_preserved_and_explicit_inactive_status_is_synced(self) -> None:
        source = StubProjectSource(
            [
                ExternalProjectRecord("ERP-A", "P-A", "Projet A"),
                ExternalProjectRecord("ERP-B", "P-B", "Projet B"),
            ]
        )
        self._sync(source)

        source.rows = [
            ExternalProjectRecord(
                "ERP-A",
                "P-A",
                "Projet A",
                status="Inactive",
            )
        ]
        result = self._sync(source)
        self.assertEqual(result.updated, 1)

        with self.factory() as session:
            rows = {row.number: row for row in session.scalars(select(Project)).all()}
            self.assertEqual(set(rows), {"P-A", "P-B"})
            self.assertEqual(rows["P-A"].status, "Inactive")
            self.assertEqual(rows["P-B"].name, "Projet B")


if __name__ == "__main__":
    unittest.main()
