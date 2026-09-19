from __future__ import annotations

from functools import partial

from datetime import date, time
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.infrastructure.sql import (
    Base,
    CommandIdempotencyReceipt,
    Project,
    Resource,
    ResourceAvailabilityRule,
    ResourceRequirement,
    Shift,
    WorkforceRequest,
    create_session_factory,
    create_sql_engine,
    transactional_session,
)
from app.server import create_api_app


WORK_DAY = date(2026, 8, 24)


from tests.http_test_auth import TEST_ADMIN_AUTH_RESOLVER

create_api_app = partial(create_api_app, auth_resolver=TEST_ADMIN_AUTH_RESOLVER)

class ServerIdempotencyTests(unittest.TestCase):
    def _database(self, directory: str) -> str:
        path = Path(directory) / "idempotency.db"
        url = f"sqlite:///{path.as_posix()}"
        engine = create_sql_engine(url)
        Base.metadata.create_all(engine)
        factory = create_session_factory(engine)
        with transactional_session(factory) as session:
            session.add(Project(id="P1", number="P-1", name="Projet API"))
            session.add(Resource(id="R1", name="Alice", active=True))
            session.flush()
            session.add(
                ResourceAvailabilityRule(
                    id="STD-R1",
                    resource_id="R1",
                    availability_type="Horaire standard",
                    weekdays="Lun,Mar,Mer,Jeu,Ven",
                    start_time=time(8, 0),
                    end_time=time(16, 0),
                    active=True,
                )
            )
        engine.dispose()
        return url

    @staticmethod
    def _count(database_url: str, model) -> int:
        engine = create_sql_engine(database_url)
        factory = create_session_factory(engine)
        try:
            with factory() as session:
                value = session.scalar(select(func.count()).select_from(model))
                return int(value or 0)
        finally:
            engine.dispose()

    def test_same_demand_key_replays_same_result_without_duplicate_write(self) -> None:
        with TemporaryDirectory() as directory:
            database_url = self._database(directory)
            app = create_api_app(database_url, actor_name="Jean")
            body = {
                "project_number": "P-1",
                "desired_start": WORK_DAY.isoformat(),
                "description": "Demande idempotente",
            }
            headers = {"Idempotency-Key": "demand-retry-1"}

            with TestClient(app, raise_server_exceptions=False) as client:
                first = client.post("/api/v1/demands", json=body, headers=headers)
                second = client.post("/api/v1/demands", json=body, headers=headers)

            self.assertEqual(first.status_code, 201, first.text)
            self.assertEqual(second.status_code, 201, second.text)
            self.assertEqual(second.json(), first.json())
            self.assertEqual(self._count(database_url, WorkforceRequest), 1)
            self.assertEqual(self._count(database_url, CommandIdempotencyReceipt), 1)

    def test_same_key_with_different_payload_is_a_conflict(self) -> None:
        with TemporaryDirectory() as directory:
            database_url = self._database(directory)
            app = create_api_app(database_url, actor_name="Jean")
            headers = {"Idempotency-Key": "demand-retry-2"}
            base = {
                "project_number": "P-1",
                "desired_start": WORK_DAY.isoformat(),
                "description": "Version A",
            }

            with TestClient(app, raise_server_exceptions=False) as client:
                first = client.post("/api/v1/demands", json=base, headers=headers)
                changed = client.post(
                    "/api/v1/demands",
                    json={**base, "description": "Version B"},
                    headers=headers,
                )

            self.assertEqual(first.status_code, 201, first.text)
            self.assertEqual(changed.status_code, 409, changed.text)
            self.assertEqual(
                changed.json()["error"]["code"],
                "idempotency_key_conflict",
            )
            self.assertEqual(self._count(database_url, WorkforceRequest), 1)
            self.assertEqual(self._count(database_url, CommandIdempotencyReceipt), 1)

    def test_failed_command_does_not_consume_key_or_leave_receipt(self) -> None:
        with TemporaryDirectory() as directory:
            database_url = self._database(directory)
            app = create_api_app(database_url, actor_name="Jean")
            headers = {"Idempotency-Key": "retry-after-failure"}

            with TestClient(app, raise_server_exceptions=False) as client:
                failed = client.post(
                    "/api/v1/demands",
                    json={
                        "project_number": "P-MISSING",
                        "desired_start": WORK_DAY.isoformat(),
                    },
                    headers=headers,
                )
                succeeded = client.post(
                    "/api/v1/demands",
                    json={
                        "project_number": "P-1",
                        "desired_start": WORK_DAY.isoformat(),
                    },
                    headers=headers,
                )

            self.assertEqual(failed.status_code, 404, failed.text)
            self.assertEqual(succeeded.status_code, 201, succeeded.text)
            self.assertEqual(self._count(database_url, WorkforceRequest), 1)
            self.assertEqual(self._count(database_url, CommandIdempotencyReceipt), 1)

    def test_quick_shift_retry_replays_same_locked_shift(self) -> None:
        with TemporaryDirectory() as directory:
            database_url = self._database(directory)
            app = create_api_app(database_url, actor_name="Jean")
            body = {
                "project_number": "P-1",
                "technician": "Alice",
                "day": WORK_DAY.isoformat(),
                "hours": 4,
                "description": "Urgence idempotente",
            }
            headers = {"Idempotency-Key": "quick-shift-retry-1"}

            with TestClient(app, raise_server_exceptions=False) as client:
                first = client.post("/api/v1/quick-shifts", json=body, headers=headers)
                second = client.post("/api/v1/quick-shifts", json=body, headers=headers)

            self.assertEqual(first.status_code, 201, first.text)
            self.assertEqual(second.status_code, 201, second.text)
            self.assertEqual(second.json(), first.json())
            self.assertEqual(self._count(database_url, ResourceRequirement), 1)
            self.assertEqual(self._count(database_url, Shift), 1)
            self.assertEqual(self._count(database_url, WorkforceRequest), 0)
            self.assertEqual(self._count(database_url, CommandIdempotencyReceipt), 1)

    def test_openapi_marks_all_creation_endpoints_with_optional_idempotency_header(self) -> None:
        with TemporaryDirectory() as directory:
            database_url = self._database(directory)
            app = create_api_app(database_url)
            with TestClient(app) as client:
                schema = client.get("/openapi.json").json()

            operations = (
                ("/api/v1/demands", "post"),
                ("/api/v1/segments", "post"),
                ("/api/v1/segments/{segment_id}/allocations", "post"),
                ("/api/v1/quick-shifts", "post"),
            )
            for path, method in operations:
                parameters = schema["paths"][path][method].get("parameters", [])
                idempotency = [
                    parameter
                    for parameter in parameters
                    if parameter.get("name") == "Idempotency-Key"
                    and parameter.get("in") == "header"
                ]
                self.assertEqual(len(idempotency), 1, f"Missing header on {method} {path}")
                self.assertFalse(idempotency[0].get("required", False))


if __name__ == "__main__":
    unittest.main()
