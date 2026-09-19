from __future__ import annotations

from functools import partial

from datetime import date, time
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.infrastructure.sql import (
    Base,
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


WORK_DAY = date(2026, 8, 24)  # lundi


from tests.http_test_auth import TEST_ADMIN_AUTH_RESOLVER, test_admin_auth_resolver

create_api_app = partial(create_api_app, auth_resolver=TEST_ADMIN_AUTH_RESOLVER)

class ServerCommandRouteTests(unittest.TestCase):
    def _database(self, directory: str) -> tuple[str, Path]:
        path = Path(directory) / "api.db"
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
        return url, path

    def test_create_and_patch_demand_use_canonical_http_fields(self) -> None:
        with TemporaryDirectory() as directory:
            database_url, _ = self._database(directory)
            app = create_api_app(\n                database_url,\n                actor_name="Jean",\n                auth_resolver=test_admin_auth_resolver("Jean"),\n            )
            with TestClient(app, raise_server_exceptions=False) as client:
                created = client.post(
                    "/api/v1/demands",
                    json={
                        "project_number": "P-1",
                        "desired_start": "2026-08-24",
                        "desired_end": "2026-08-25",
                        "description": "À effacer",
                        "resource_count": 1,
                    },
                )
                self.assertEqual(created.status_code, 201, created.text)
                number = created.json()["demand_number"]
                self.assertEqual(created.json()["status"], "Brouillon")

                patched = client.patch(
                    f"/api/v1/demands/{number}",
                    json={"description": None},
                )
                self.assertEqual(patched.status_code, 200, patched.text)
                self.assertFalse(patched.json()["reapproval_required"])

            engine = create_sql_engine(database_url)
            factory = create_session_factory(engine)
            try:
                with factory() as session:
                    request = session.scalar(
                        select(WorkforceRequest).where(
                            WorkforceRequest.legacy_demand_number == number
                        )
                    )
                    self.assertIsNotNone(request)
                    assert request is not None
                    self.assertEqual(request.requester_name, "Jean")
                    self.assertIsNone(request.description)
            finally:
                engine.dispose()

    def test_unknown_project_returns_structured_not_found(self) -> None:
        with TemporaryDirectory() as directory:
            database_url, _ = self._database(directory)
            app = create_api_app(database_url)
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.post(
                    "/api/v1/demands",
                    json={
                        "project_number": "P-UNKNOWN",
                        "desired_start": "2026-08-24",
                    },
                )

            self.assertEqual(response.status_code, 404)
            payload = response.json()["error"]
            self.assertEqual(payload["code"], "demand_create_not_found")
            self.assertIn("Projet P-UNKNOWN", payload["message"])

    def test_unknown_http_field_is_rejected_and_not_silently_ignored(self) -> None:
        with TemporaryDirectory() as directory:
            database_url, _ = self._database(directory)
            app = create_api_app(database_url)
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.post(
                    "/api/v1/demands",
                    json={
                        "project_number": "P-1",
                        "desired_start": "2026-08-24",
                        "NumeroProjet": "legacy-field-must-not-work",
                    },
                )

            self.assertEqual(response.status_code, 422)
            payload = response.json()["error"]
            self.assertEqual(payload["code"], "request_validation_error")
            locations = [item["location"] for item in payload["context"]["errors"]]
            self.assertTrue(any("NumeroProjet" in location for location in locations))

            engine = create_sql_engine(database_url)
            factory = create_session_factory(engine)
            try:
                with factory() as session:
                    count = session.scalar(
                        select(func.count()).select_from(WorkforceRequest)
                    )
                    self.assertEqual(int(count or 0), 0)
            finally:
                engine.dispose()

    def test_segment_patch_rejects_explicit_null_for_non_nullable_boolean(self) -> None:
        with TemporaryDirectory() as directory:
            database_url, _ = self._database(directory)
            app = create_api_app(database_url)
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.patch(
                    "/api/v1/segments/SEG-UNKNOWN",
                    json={"outside_standard_hours": None},
                )

            self.assertEqual(response.status_code, 422)
            payload = response.json()["error"]
            self.assertEqual(payload["code"], "request_validation_error")
            locations = [item["location"] for item in payload["context"]["errors"]]
            self.assertTrue(any("outside_standard_hours" in location for location in locations))

    def test_quick_shift_route_creates_locked_shift_without_fake_request(self) -> None:
        with TemporaryDirectory() as directory:
            database_url, _ = self._database(directory)
            app = create_api_app(\n                database_url,\n                actor_name="Jean",\n                auth_resolver=test_admin_auth_resolver("Jean"),\n            )
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.post(
                    "/api/v1/quick-shifts",
                    json={
                        "project_number": "P-1",
                        "technician": "Alice",
                        "day": WORK_DAY.isoformat(),
                        "hours": 4,
                        "description": "Urgence",
                    },
                )

            self.assertEqual(response.status_code, 201, response.text)
            result = response.json()
            self.assertTrue(result["segment_id"])
            self.assertTrue(result["allocation_id"])

            engine = create_sql_engine(database_url)
            factory = create_session_factory(engine)
            try:
                with factory() as session:
                    requirement = session.scalar(
                        select(ResourceRequirement).where(
                            ResourceRequirement.legacy_segment_id == result["segment_id"]
                        )
                    )
                    shift = session.scalar(
                        select(Shift).where(
                            Shift.legacy_allocation_id == result["allocation_id"]
                        )
                    )
                    request_count = session.scalar(
                        select(func.count()).select_from(WorkforceRequest)
                    )
                    self.assertIsNotNone(requirement)
                    assert requirement is not None
                    self.assertIsNone(requirement.workforce_request_id)
                    self.assertEqual(requirement.origin, "QUICK_SHIFT")
                    self.assertIsNotNone(shift)
                    assert shift is not None
                    self.assertTrue(shift.locked)
                    self.assertEqual(float(shift.hours), 4.0)
                    self.assertEqual(int(request_count or 0), 0)
            finally:
                engine.dispose()

    def test_openapi_exposes_canonical_contract_not_excel_column_names(self) -> None:
        with TemporaryDirectory() as directory:
            database_url, _ = self._database(directory)
            app = create_api_app(database_url)
            with TestClient(app) as client:
                response = client.get("/openapi.json")

            self.assertEqual(response.status_code, 200)
            serialized = json.dumps(response.json(), ensure_ascii=False)
            self.assertIn("project_number", serialized)
            self.assertIn("desired_start", serialized)
            self.assertIn("source_effort_id", serialized)
            for legacy in (
                "NumeroProjet",
                "DateDebutSouhaitee",
                "HeuresPrevues",
                "IDSegment",
                "IDAllocation",
                "source_effort_row",
                "SourceEffortRow",
            ):
                self.assertNotIn(legacy, serialized)


if __name__ == "__main__":
    unittest.main()
