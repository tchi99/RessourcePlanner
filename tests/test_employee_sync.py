from __future__ import annotations

import unittest

from sqlalchemy import select

from app.application.employee_sync import EmployeeSyncService, ExternalEmployeeRecord
from app.application.errors import ApplicationConflictError
from app.infrastructure.sql import (
    Base,
    Resource,
    SqlEmployeeSyncRepository,
    create_session_factory,
    create_sql_engine,
    transactional_session,
)


class StubEmployeeSource:
    def __init__(self, rows: list[ExternalEmployeeRecord]) -> None:
        self.rows = rows

    def list_employees(self) -> tuple[ExternalEmployeeRecord, ...]:
        return tuple(self.rows)


class EmployeeSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_sql_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.factory = create_session_factory(self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()

    def _sync(self, source: StubEmployeeSource):
        with transactional_session(self.factory) as session:
            return EmployeeSyncService(
                source,
                SqlEmployeeSyncRepository(session),
            ).synchronize()

    def test_sync_is_idempotent_and_preserves_planning_owned_fields(self) -> None:
        first_email = "employee1" + chr(64) + "example.invalid"
        second_email = "employee2" + chr(64) + "example.invalid"
        source = StubEmployeeSource(
            [ExternalEmployeeRecord("EMP-1", "Employé initial", first_email, True)]
        )
        first = self._sync(source)
        second = self._sync(source)
        self.assertEqual((first.created, first.updated, first.unchanged), (1, 0, 0))
        self.assertEqual((second.created, second.updated, second.unchanged), (0, 0, 1))

        with transactional_session(self.factory) as session:
            row = session.scalar(select(Resource).where(Resource.external_id == "EMP-1"))
            assert row is not None
            row.resource_class = "Programmation"
            row.competencies = "PLC;SCADA"
            row.note = "Attribut local"
            row.sort_order = 7

        source.rows[0] = ExternalEmployeeRecord(
            "EMP-1",
            "Employé renommé",
            second_email,
            False,
        )
        result = self._sync(source)
        self.assertEqual((result.created, result.updated, result.unchanged), (0, 1, 0))

        with self.factory() as session:
            row = session.scalar(select(Resource).where(Resource.external_id == "EMP-1"))
            assert row is not None
            self.assertEqual(row.name, "Employé renommé")
            self.assertEqual(row.email, second_email)
            self.assertFalse(row.active)
            self.assertEqual(row.resource_class, "Programmation")
            self.assertEqual(row.competencies, "PLC;SCADA")
            self.assertEqual(row.note, "Attribut local")
            self.assertEqual(row.sort_order, 7)

    def test_missing_employee_is_preserved_and_not_implicitly_inactivated(self) -> None:
        source = StubEmployeeSource(
            [
                ExternalEmployeeRecord("EMP-A", "Ressource A"),
                ExternalEmployeeRecord("EMP-B", "Ressource B"),
            ]
        )
        self._sync(source)
        source.rows = [ExternalEmployeeRecord("EMP-A", "Ressource A")]
        self._sync(source)

        with self.factory() as session:
            rows = {
                row.external_id: row
                for row in session.scalars(select(Resource)).all()
            }
            self.assertEqual(set(rows), {"EMP-A", "EMP-B"})
            self.assertTrue(rows["EMP-B"].active)

    def test_unlinked_manual_resource_with_same_name_fails_closed(self) -> None:
        with transactional_session(self.factory) as session:
            session.add(Resource(id="LOCAL-1", name="Même nom", active=True))

        with self.assertRaises(ApplicationConflictError) as raised:
            self._sync(
                StubEmployeeSource(
                    [ExternalEmployeeRecord("EMP-NEW", "Même nom")]
                )
            )
        self.assertEqual(raised.exception.code, "employee_sync_unlinked_name_conflict")

    def test_two_distinct_external_ids_may_have_same_name_once_linked(self) -> None:
        result = self._sync(
            StubEmployeeSource(
                [
                    ExternalEmployeeRecord("EMP-10", "Nom partagé"),
                    ExternalEmployeeRecord("EMP-11", "Nom partagé"),
                ]
            )
        )
        self.assertEqual(result.created, 2)


if __name__ == "__main__":
    unittest.main()
