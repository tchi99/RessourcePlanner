from __future__ import annotations

from functools import partial

from datetime import date, time
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from app.domain.confirmation import (
    CONFIRMATION_CONFIRMED,
    CONFIRMATION_TENTATIVE,
    effective_confirmation,
    normalize_confirmation,
)
from app.infrastructure.sql import (
    Base,
    Project,
    Resource,
    ResourceAvailabilityRule,
    create_session_factory,
    create_sql_engine,
    transactional_session,
)
from app.server import create_api_app


DAY = date(2026, 8, 24)  # lundi


from tests.http_test_auth import TEST_ADMIN_AUTH_RESOLVER

create_api_app = partial(create_api_app, auth_resolver=TEST_ADMIN_AUTH_RESOLVER)

class ConfirmationPolicyTests(unittest.TestCase):
    def test_policy_normalizes_common_confirmed_spellings_and_inherits(self) -> None:
        self.assertEqual(normalize_confirmation("Confirmé"), CONFIRMATION_CONFIRMED)
        self.assertEqual(normalize_confirmation("confirmee"), CONFIRMATION_CONFIRMED)
        self.assertEqual(normalize_confirmation("Tentative"), CONFIRMATION_TENTATIVE)
        self.assertEqual(
            effective_confirmation(None, "Tentative"),
            CONFIRMATION_TENTATIVE,
        )
        self.assertEqual(
            effective_confirmation("Confirmé", "Tentative"),
            CONFIRMATION_CONFIRMED,
        )

        with self.assertRaises(ValueError):
            normalize_confirmation("peut-être")


class ConfirmationInheritanceApiTests(unittest.TestCase):
    def _database(self, directory: str) -> str:
        path = Path(directory) / "confirmation.db"
        url = f"sqlite:///{path.as_posix()}"
        engine = create_sql_engine(url)
        Base.metadata.create_all(engine)
        factory = create_session_factory(engine)
        with transactional_session(factory) as session:
            session.add(Project(id="P1", number="P-1", name="Projet confirmation"))
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
    def _create_and_approve_tentative(client: TestClient) -> str:
        created = client.post(
            "/api/v1/demands",
            json={
                "project_number": "P-1",
                "desired_start": DAY.isoformat(),
                "desired_end": DAY.isoformat(),
                "estimated_hours": 4,
                "proposed_technician": "Alice",
                "confirmation": "Tentative",
            },
        )
        assert created.status_code == 201, created.text
        number = created.json()["demand_number"]
        submitted = client.post(f"/api/v1/demands/{number}/submit")
        assert submitted.status_code == 200, submitted.text
        approved = client.post(
            f"/api/v1/demands/{number}/approve",
            json={"comment": "ok"},
        )
        assert approved.status_code == 200, approved.text
        return number

    def test_request_confirmation_flows_to_requirement_and_auto_shift(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(self._database(directory), actor_name="Jean")
            with TestClient(app, raise_server_exceptions=False) as client:
                number = self._create_and_approve_tentative(client)

                segments = client.get("/api/v1/segments").json()
                segment = next(row for row in segments if row["demand_number"] == number)
                self.assertEqual(segment["confirmation"], "Tentative")
                self.assertFalse(segment["confirmation_overridden"])

                shifts = client.get("/api/v1/shifts").json()
                shift = next(row for row in shifts if row["segment_id"] == segment["segment_id"])
                self.assertEqual(shift["confirmation"], "Tentative")
                self.assertIsNone(shift["confirmation_override"])

    def test_segment_override_can_be_set_and_cleared_without_changing_request(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(self._database(directory), actor_name="Jean")
            with TestClient(app, raise_server_exceptions=False) as client:
                number = self._create_and_approve_tentative(client)
                segment = next(
                    row
                    for row in client.get("/api/v1/segments").json()
                    if row["demand_number"] == number
                )
                segment_id = segment["segment_id"]

                overridden = client.patch(
                    f"/api/v1/segments/{segment_id}",
                    json={"confirmation": "Confirmé"},
                )
                self.assertEqual(overridden.status_code, 200, overridden.text)
                after_override = client.get(f"/api/v1/segments/{segment_id}").json()
                self.assertEqual(after_override["confirmation"], "Confirmée")
                self.assertTrue(after_override["confirmation_overridden"])
                shift = next(
                    row
                    for row in client.get("/api/v1/shifts").json()
                    if row["segment_id"] == segment_id
                )
                self.assertEqual(shift["confirmation"], "Confirmée")
                self.assertIsNone(shift["confirmation_override"])

                inherited = client.patch(
                    f"/api/v1/segments/{segment_id}",
                    json={"confirmation": None},
                )
                self.assertEqual(inherited.status_code, 200, inherited.text)
                after_clear = client.get(f"/api/v1/segments/{segment_id}").json()
                self.assertEqual(after_clear["confirmation"], "Tentative")
                self.assertFalse(after_clear["confirmation_overridden"])

    def test_manual_shift_can_override_segment_confirmation(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(self._database(directory), actor_name="Jean")
            with TestClient(app, raise_server_exceptions=False) as client:
                number = self._create_and_approve_tentative(client)
                segment = next(
                    row
                    for row in client.get("/api/v1/segments").json()
                    if row["demand_number"] == number
                )
                created = client.post(
                    f"/api/v1/segments/{segment['segment_id']}/allocations",
                    json={
                        "technician": "Alice",
                        "day": DAY.isoformat(),
                        "hours": 4,
                        "confirmation": "Confirmée",
                    },
                )
                self.assertEqual(created.status_code, 201, created.text)
                allocation_id = created.json()["allocation_id"]

                shift = next(
                    row
                    for row in client.get("/api/v1/shifts").json()
                    if row["allocation_id"] == allocation_id
                )
                self.assertEqual(shift["confirmation"], "Confirmée")
                self.assertEqual(shift["confirmation_override"], "Confirmée")

    def test_quick_shift_confirmation_is_owned_by_adhoc_requirement_and_inherited_by_shift(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(self._database(directory), actor_name="Jean")
            with TestClient(app, raise_server_exceptions=False) as client:
                created = client.post(
                    "/api/v1/quick-shifts",
                    json={
                        "project_number": "P-1",
                        "technician": "Alice",
                        "day": DAY.isoformat(),
                        "hours": 4,
                        "confirmation": "Tentative",
                    },
                )
                self.assertEqual(created.status_code, 201, created.text)
                result = created.json()

                segment = client.get(
                    f"/api/v1/segments/{result['segment_id']}"
                ).json()
                self.assertEqual(segment["confirmation"], "Tentative")
                self.assertFalse(segment["confirmation_overridden"])

                shift = next(
                    row
                    for row in client.get("/api/v1/shifts").json()
                    if row["allocation_id"] == result["allocation_id"]
                )
                self.assertEqual(shift["confirmation"], "Tentative")
                self.assertIsNone(shift["confirmation_override"])

    def test_period_confirmation_overrides_request_snapshot_at_approval(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(self._database(directory), actor_name="Jean")
            with TestClient(app, raise_server_exceptions=False) as client:
                created = client.post(
                    "/api/v1/demands",
                    json={
                        "project_number": "P-1",
                        "desired_start": DAY.isoformat(),
                        "desired_end": DAY.isoformat(),
                        "confirmation": "Confirmée",
                    },
                )
                self.assertEqual(created.status_code, 201, created.text)
                number = created.json()["demand_number"]
                replaced = client.put(
                    f"/api/v1/demands/{number}/periods",
                    json={
                        "periods": [
                            {
                                "period_id": "PER-1",
                                "start_date": DAY.isoformat(),
                                "end_date": DAY.isoformat(),
                                "hours": 4,
                                "confirmation": "Tentative",
                                "proposed_resource": "Alice",
                            }
                        ]
                    },
                )
                self.assertEqual(replaced.status_code, 200, replaced.text)
                self.assertEqual(
                    client.post(f"/api/v1/demands/{number}/submit").status_code,
                    200,
                )
                approved = client.post(
                    f"/api/v1/demands/{number}/approve",
                    json={"comment": "ok"},
                )
                self.assertEqual(approved.status_code, 200, approved.text)

                segment = next(
                    row
                    for row in client.get("/api/v1/segments").json()
                    if row["demand_number"] == number
                )
                self.assertEqual(segment["confirmation"], "Tentative")
                self.assertFalse(segment["confirmation_overridden"])


if __name__ == "__main__":
    unittest.main()
