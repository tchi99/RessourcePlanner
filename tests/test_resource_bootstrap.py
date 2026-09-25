from __future__ import annotations

from datetime import time
import unittest

from sqlalchemy import select

from app.application.errors import ApplicationConflictError
from app.application.resource_bootstrap import (
    BootstrapResourceRecord,
    BootstrapStandardSchedule,
    ResourceBootstrapService,
)
from app.infrastructure.sql import (
    Base,
    Resource,
    ResourceAvailabilityRule,
    SqlResourceAdminRepository,
    create_session_factory,
    create_sql_engine,
    transactional_session,
)


class StubSource:
    def __init__(self, rows: list[BootstrapResourceRecord]) -> None:
        self.rows = rows

    def list_resources(self) -> tuple[BootstrapResourceRecord, ...]:
        return tuple(self.rows)


class ResourceBootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_sql_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.factory = create_session_factory(self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()

    def _sync(self, rows: list[BootstrapResourceRecord]):
        with transactional_session(self.factory) as session:
            return ResourceBootstrapService(
                StubSource(rows), SqlResourceAdminRepository(session)
            ).synchronize()

    @staticmethod
    def schedule(start: int = 7, end: int = 15) -> BootstrapStandardSchedule:
        return BootstrapStandardSchedule(
            "Lun,Mar,Mer,Jeu,Ven", time(start, 0), time(end, 0)
        )

    def test_replay_is_idempotent_and_schedule_is_explicit(self) -> None:
        row = BootstrapResourceRecord(
            "EMP-TEST-001", "Technicien Test 001", None, True,
            "Automatisation", 10, self.schedule(),
        )
        first = self._sync([row])
        replay = self._sync([row])
        self.assertEqual((first.created, first.updated, first.unchanged), (1, 0, 0))
        self.assertEqual(first.schedules_created, 1)
        self.assertEqual((replay.created, replay.updated, replay.unchanged), (0, 0, 1))
        self.assertEqual(replay.schedules_unchanged, 1)

    def test_owned_fields_update_without_overwriting_local_data(self) -> None:
        email1 = "resource1" + chr(64) + "example.invalid"
        email2 = "resource2" + chr(64) + "example.invalid"
        self._sync([
            BootstrapResourceRecord(
                "EMP-TEST-002", "Technicien Test 002", email1, True,
                "Automatisation", 4,
            )
        ])
        with transactional_session(self.factory) as session:
            row = session.scalar(select(Resource).where(Resource.external_id == "EMP-TEST-002"))
            assert row is not None
            row.competencies = "PLC;SCADA"
            row.note = "Donnée locale synthétique"

        result = self._sync([
            BootstrapResourceRecord(
                "EMP-TEST-002", "Technicien Test renommé", email2, False,
                "Mise en service", 8,
            )
        ])
        self.assertEqual((result.created, result.updated, result.unchanged), (0, 1, 0))
        with self.factory() as session:
            row = session.scalar(select(Resource).where(Resource.external_id == "EMP-TEST-002"))
            assert row is not None
            self.assertEqual(row.email, email2)
            self.assertEqual(row.resource_class, "Mise en service")
            self.assertEqual(row.sort_order, 8)
            self.assertEqual(row.competencies, "PLC;SCADA")
            self.assertEqual(row.note, "Donnée locale synthétique")

    def test_missing_resource_is_preserved(self) -> None:
        self._sync([
            BootstrapResourceRecord("EMP-A", "Ressource Test A", None, True, "Automatisation"),
            BootstrapResourceRecord("EMP-B", "Ressource Test B", None, True, "Automatisation"),
        ])
        self._sync([
            BootstrapResourceRecord("EMP-A", "Ressource Test A", None, True, "Automatisation")
        ])
        with self.factory() as session:
            rows = {row.external_id: row for row in session.scalars(select(Resource)).all()}
        self.assertEqual(set(rows), {"EMP-A", "EMP-B"})
        self.assertTrue(rows["EMP-B"].active)

    def test_different_existing_schedule_is_preserved(self) -> None:
        self._sync([
            BootstrapResourceRecord(
                "EMP-C", "Ressource Test C", None, True,
                "Automatisation", standard_schedule=self.schedule(7, 15),
            )
        ])
        result = self._sync([
            BootstrapResourceRecord(
                "EMP-C", "Ressource Test C", None, True,
                "Automatisation", standard_schedule=self.schedule(8, 16),
            )
        ])
        self.assertEqual(result.schedules_preserved, 1)
        with self.factory() as session:
            rule = session.scalar(select(ResourceAvailabilityRule))
            assert rule is not None
            self.assertEqual((rule.start_time, rule.end_time), (time(7, 0), time(15, 0)))

    def test_unlinked_same_name_fails_closed(self) -> None:
        with transactional_session(self.factory) as session:
            session.add(Resource(id="LOCAL-1", name="Ressource Test D", external_id=None))
        with self.assertRaises(ApplicationConflictError) as raised:
            self._sync([
                BootstrapResourceRecord(
                    "EMP-D", "Ressource Test D", None, True, "Automatisation"
                )
            ])
        self.assertEqual(raised.exception.code, "resource_bootstrap_unlinked_name_conflict")


if __name__ == "__main__":
    unittest.main()
