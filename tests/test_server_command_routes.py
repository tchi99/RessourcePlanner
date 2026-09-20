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
    Competency,
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
            session.add(Competency(id="C1", name="PLC", active=True, sort_order=0))
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
            app = create_api_app(
                database_url,
                actor_name="Jean",
                auth_resolver=test_admin_auth_resolver("Jean"),
            )
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

    def test_multi_line_demand_write_resolves_default_hours_and_versions(self) -> None:
        with TemporaryDirectory() as directory:
            database_url, _ = self._database(directory)
            app = create_api_app(
                database_url,
                actor_name="Jean",
                auth_resolver=test_admin_auth_resolver("Jean"),
            )
            with TestClient(app, raise_server_exceptions=False) as client:
                created = client.post(
                    "/api/v1/demands",
                    json={
                        "project_number": "P-1",
                        "description": "Demande à deux besoins",
                        "lines": [
                            {
                                "required_resource_class": "Automatisation",
                                "required_competency_ids": ["C1"],
                                "proposed_resource_id": "R1",
                                "desired_start": "2026-08-24",
                                "desired_end": "2026-08-26",
                                "desired_active_days": 3
                            },
                            {
                                "required_resource_class": "Électricité",
                                "desired_start": "2026-08-27",
                                "desired_end": "2026-08-28",
                                "desired_active_days": 2,
                                "estimated_hours": 12
                            }
                        ]
                    },
                )
                self.assertEqual(created.status_code, 201, created.text)
                number = created.json()["demand_number"]

                read = client.get(f"/api/v1/demands/{number}")
                self.assertEqual(read.status_code, 200, read.text)
                demand = read.json()
                self.assertTrue(demand["line_mode"])
                self.assertEqual(demand["version"], 1)
                self.assertEqual(demand["resource_count"], 2)
                self.assertEqual(demand["estimated_hours"], 36.0)
                self.assertEqual(len(demand["lines"]), 2)
                active = [line for line in demand["lines"] if line["active"]]
                self.assertEqual(len(active), 2)
                self.assertEqual(active[0]["estimated_hours"], 24.0)
                self.assertEqual(active[0]["estimated_hours_source"], "DEFAULT_8H")
                self.assertEqual(active[0]["default_hours_per_day"], 8.0)
                self.assertEqual(active[0]["required_competency_ids"], ["C1"])
                self.assertEqual(active[0]["proposed_resource_id"], "R1")
                self.assertEqual(active[0]["proposed_resource"], "Alice")
                self.assertEqual(active[1]["estimated_hours"], 12.0)
                self.assertEqual(active[1]["estimated_hours_source"], "EXPLICIT")

                first_id = active[0]["line_id"]
                removed_id = active[1]["line_id"]
                patched = client.patch(
                    f"/api/v1/demands/{number}",
                    json={
                        "expected_version": 1,
                        "lines": [
                            {
                                "id": first_id,
                                "required_resource_class": "Automatisation",
                                "required_competency_ids": ["C1"],
                                "proposed_resource_id": "R1",
                                "desired_start": "2026-08-24",
                                "desired_end": "2026-08-26",
                                "desired_active_days": 3
                            },
                            {
                                "required_resource_class": "Instrumentation",
                                "desired_start": "2026-08-31",
                                "desired_end": "2026-09-01",
                                "estimated_hours": 8
                            }
                        ]
                    },
                )
                self.assertEqual(patched.status_code, 200, patched.text)

                updated = client.get(f"/api/v1/demands/{number}").json()
                self.assertEqual(updated["version"], 2)
                active = [line for line in updated["lines"] if line["active"]]
                inactive = [line for line in updated["lines"] if not line["active"]]
                self.assertEqual(len(active), 2)
                self.assertEqual(len(inactive), 1)
                self.assertEqual(active[0]["line_id"], first_id)
                self.assertEqual(inactive[0]["line_id"], removed_id)
                self.assertEqual(updated["estimated_hours"], 32.0)

                stale = client.patch(
                    f"/api/v1/demands/{number}",
                    json={
                        "expected_version": 1,
                        "lines": [
                            {
                                "id": first_id,
                                "desired_start": "2026-08-24",
                                "desired_active_days": 1
                            }
                        ]
                    },
                )
                self.assertEqual(stale.status_code, 409, stale.text)
                self.assertEqual(
                    stale.json()["error"]["code"],
                    "demand_version_conflict",
                )

    def test_legacy_single_line_can_switch_authority_without_changing_line_id(self) -> None:
        with TemporaryDirectory() as directory:
            database_url, _ = self._database(directory)
            app = create_api_app(database_url)
            with TestClient(app, raise_server_exceptions=False) as client:
                created = client.post(
                    "/api/v1/demands",
                    json={
                        "project_number": "P-1",
                        "desired_start": "2026-08-24",
                        "estimated_hours": 8
                    },
                )
                self.assertEqual(created.status_code, 201, created.text)
                number = created.json()["demand_number"]
                legacy = client.get(f"/api/v1/demands/{number}").json()
                self.assertFalse(legacy["line_mode"])
                self.assertEqual(len(legacy["lines"]), 1)
                legacy_line_id = legacy["lines"][0]["line_id"]

                converted = client.patch(
                    f"/api/v1/demands/{number}",
                    json={
                        "expected_version": legacy["version"],
                        "lines": [
                            {
                                "id": legacy_line_id,
                                "desired_start": "2026-08-24",
                                "desired_active_days": 1
                            }
                        ]
                    },
                )
                self.assertEqual(converted.status_code, 200, converted.text)

                current = client.get(f"/api/v1/demands/{number}").json()
                self.assertTrue(current["line_mode"])
                self.assertEqual(current["lines"][0]["line_id"], legacy_line_id)
                self.assertEqual(current["lines"][0]["estimated_hours"], 8.0)
                self.assertEqual(
                    current["lines"][0]["estimated_hours_source"],
                    "DEFAULT_8H",
                )

                flat_edit = client.patch(
                    f"/api/v1/demands/{number}",
                    json={"estimated_hours": 4},
                )
                self.assertEqual(flat_edit.status_code, 422, flat_edit.text)
                self.assertEqual(
                    flat_edit.json()["error"]["code"],
                    "demand_update_invalid",
                )

    def test_multi_line_payload_cannot_mix_legacy_need_fields(self) -> None:
        with TemporaryDirectory() as directory:
            database_url, _ = self._database(directory)
            app = create_api_app(database_url)
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.post(
                    "/api/v1/demands",
                    json={
                        "project_number": "P-1",
                        "desired_start": "2026-08-24",
                        "lines": [
                            {
                                "desired_start": "2026-08-24",
                                "estimated_hours": 8
                            }
                        ]
                    },
                )
            self.assertEqual(response.status_code, 422, response.text)
            self.assertEqual(
                response.json()["error"]["code"],
                "request_validation_error",
            )

    def test_line_authored_demand_can_be_approved_with_288e(self) -> None:
        with TemporaryDirectory() as directory:
            database_url, _ = self._database(directory)
            app = create_api_app(database_url)
            with TestClient(app, raise_server_exceptions=False) as client:
                created = client.post(
                    "/api/v1/demands",
                    json={
                        "project_number": "P-1",
                        "submit": True,
                        "lines": [
                            {
                                "desired_start": "2026-08-24",
                                "desired_active_days": 1
                            }
                        ]
                    },
                )
                self.assertEqual(created.status_code, 201, created.text)
                number = created.json()["demand_number"]
                approved = client.post(
                    f"/api/v1/demands/{number}/approve",
                    json={"comment": "test"},
                )

            self.assertEqual(approved.status_code, 200, approved.text)
            self.assertEqual(approved.json()["status"], "En planification")

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
            app = create_api_app(
                database_url,
                actor_name="Jean",
                auth_resolver=test_admin_auth_resolver("Jean"),
            )
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
