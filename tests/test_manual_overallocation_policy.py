from __future__ import annotations

from functools import partial

from datetime import date, time
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.domain.manual_overallocation import manual_overallocation_impact
from app.infrastructure.sql import (
    Base,
    PlanningChangeHistory,
    Project,
    Resource,
    ResourceAvailabilityRule,
    ResourceRequirement,
    Shift,
    WorkforceRequest,
    create_session_factory,
    create_sql_engine,
)
from app.server import create_api_app


from tests.http_test_auth import TEST_ADMIN_AUTH_RESOLVER

create_api_app = partial(create_api_app, auth_resolver=TEST_ADMIN_AUTH_RESOLVER)

class ManualOverallocationPolicyTests(unittest.TestCase):
    def test_impact_detects_only_an_increase_of_the_exception(self) -> None:
        created = manual_overallocation_impact(
            planned_hours=8,
            current_locked_hours=8,
            projected_locked_hours=12,
        )
        self.assertEqual(created.current_excess_hours, 0)
        self.assertEqual(created.projected_excess_hours, 4)
        self.assertTrue(created.increases_exception)

        reduced = manual_overallocation_impact(
            planned_hours=8,
            current_locked_hours=12,
            projected_locked_hours=10,
        )
        self.assertEqual(reduced.current_excess_hours, 4)
        self.assertEqual(reduced.projected_excess_hours, 2)
        self.assertFalse(reduced.increases_exception)


class ManualOverallocationHttpTests(unittest.TestCase):
    @staticmethod
    def _database(directory: str) -> tuple[str, date]:
        path = Path(directory) / "manual-overallocation.db"
        url = f"sqlite:///{path.as_posix()}"
        engine = create_sql_engine(url)
        Base.metadata.create_all(engine)
        factory = create_session_factory(engine)
        today = date.today()
        with factory.begin() as session:
            session.add(Project(id="P1", number="P-1", name="Projet surallocation"))
            session.add(Resource(id="R1", name="Alice", active=True))
            session.flush()
            session.add(
                ResourceAvailabilityRule(
                    id="STD-R1",
                    resource_id="R1",
                    availability_type="Horaire standard",
                    weekdays="Lun,Mar,Mer,Jeu,Ven,Sam,Dim",
                    start_time=time(8, 0),
                    end_time=time(20, 0),
                    active=True,
                )
            )
            session.add(
                WorkforceRequest(
                    id="WR1",
                    legacy_demand_number="D-1",
                    project_id="P1",
                    desired_start=today,
                    desired_end=today,
                    status="En planification",
                )
            )
            session.flush()
            for suffix in ("1", "2"):
                session.add(
                    ResourceRequirement(
                        id=f"REQ{suffix}",
                        legacy_segment_id=f"SEG-{suffix}",
                        project_id="P1",
                        workforce_request_id="WR1",
                        assigned_resource_id="R1",
                        start_date=today,
                        end_date=today,
                        planned_hours=8,
                        status="Planifié",
                        planning_type="Flexible",
                        confirmation="Confirmée",
                    )
                )
        engine.dispose()
        return url, today

    @staticmethod
    def _manual_payload(today: date, hours: float, policy: str | None = None) -> dict[str, object]:
        payload: dict[str, object] = {
            "technician": "Alice",
            "day": today.isoformat(),
            "hours": hours,
            "outside_standard_hours": False,
            "note": "Test surallocation",
            "confirmation": None,
        }
        if policy is not None:
            payload["overallocation_policy"] = policy
        return payload

    def test_keep_exception_is_explicit_visible_audited_and_rebuild_safe(self) -> None:
        with TemporaryDirectory() as directory:
            database_url, today = self._database(directory)
            app = create_api_app(database_url, actor_name="coord-surallocation")

            with TestClient(app, raise_server_exceptions=False) as client:
                first = client.post(
                    "/api/v1/segments/SEG-1/allocations",
                    json=self._manual_payload(today, 8),
                    headers={"Idempotency-Key": "seg1-first"},
                )
                self.assertEqual(first.status_code, 201, first.text)

                blocked = client.post(
                    "/api/v1/segments/SEG-1/allocations",
                    json=self._manual_payload(today, 4),
                    headers={"Idempotency-Key": "seg1-blocked"},
                )
                self.assertEqual(blocked.status_code, 422, blocked.text)
                error = blocked.json()["error"]
                self.assertEqual(error["code"], "allocation_overallocation_choice_required")
                self.assertEqual(error["context"]["planned_hours"], 8.0)
                self.assertEqual(error["context"]["current_locked_hours"], 8.0)
                self.assertEqual(error["context"]["projected_locked_hours"], 12.0)
                self.assertEqual(error["context"]["excess_hours"], 4.0)

                kept = client.post(
                    "/api/v1/segments/SEG-1/allocations",
                    json=self._manual_payload(today, 4, "KEEP_EXCEPTION"),
                    headers={"Idempotency-Key": "seg1-kept"},
                )
                self.assertEqual(kept.status_code, 201, kept.text)

                segment = client.get("/api/v1/segments/SEG-1")
                self.assertEqual(segment.status_code, 200, segment.text)
                body = segment.json()
                self.assertEqual(body["planned_hours"], 8.0)
                self.assertEqual(body["locked_hours"], 12.0)
                self.assertEqual(body["overallocated_hours"], 4.0)
                self.assertTrue(body["overallocated"])

                shifts = client.get(
                    "/api/v1/shifts",
                    params={"start": today.isoformat(), "end": today.isoformat()},
                )
                self.assertEqual(shifts.status_code, 200, shifts.text)
                segment_shifts = [row for row in shifts.json() if row["segment_id"] == "SEG-1"]
                self.assertEqual(sum(row["hours"] for row in segment_shifts if row["locked"]), 12.0)
                self.assertTrue(all(row["segment_overallocated_hours"] == 4.0 for row in segment_shifts))

                history = client.get("/api/v1/segments/SEG-1/history")
                self.assertEqual(history.status_code, 200, history.text)
                self.assertIn(
                    "Dérogation surallocation manuelle",
                    [row["action"] for row in history.json()],
                )

                rebuilt = client.post("/api/v1/planning/rebuild")
                self.assertEqual(rebuilt.status_code, 200, rebuilt.text)

            engine = create_sql_engine(database_url)
            factory = create_session_factory(engine)
            with factory() as session:
                locked = session.scalars(
                    select(Shift).where(
                        Shift.resource_requirement_id == "REQ1",
                        Shift.locked.is_(True),
                    )
                ).all()
                self.assertEqual(sum(float(row.hours) for row in locked), 12.0)
                self.assertEqual(len(locked), 2)
            engine.dispose()

    def test_increase_planned_regularizes_at_creation_time(self) -> None:
        with TemporaryDirectory() as directory:
            database_url, today = self._database(directory)
            app = create_api_app(database_url, actor_name="coord-surallocation")

            with TestClient(app, raise_server_exceptions=False) as client:
                first = client.post(
                    "/api/v1/segments/SEG-2/allocations",
                    json=self._manual_payload(today, 8),
                    headers={"Idempotency-Key": "seg2-first"},
                )
                self.assertEqual(first.status_code, 201, first.text)

                increased = client.post(
                    "/api/v1/segments/SEG-2/allocations",
                    json=self._manual_payload(today, 4, "INCREASE_PLANNED"),
                    headers={"Idempotency-Key": "seg2-increase"},
                )
                self.assertEqual(increased.status_code, 201, increased.text)

                segment = client.get("/api/v1/segments/SEG-2").json()
                self.assertEqual(segment["planned_hours"], 12.0)
                self.assertEqual(segment["locked_hours"], 12.0)
                self.assertEqual(segment["overallocated_hours"], 0.0)
                self.assertFalse(segment["overallocated"])

                history = client.get("/api/v1/segments/SEG-2/history")
                self.assertEqual(history.status_code, 200, history.text)
                self.assertIn(
                    "Augmentation heures prévues depuis quart manuel",
                    [row["action"] for row in history.json()],
                )

    def test_reducing_planned_hours_requires_explicit_segment_exception(self) -> None:
        with TemporaryDirectory() as directory:
            database_url, today = self._database(directory)
            app = create_api_app(database_url, actor_name="coord-surallocation")

            with TestClient(app, raise_server_exceptions=False) as client:
                first = client.post(
                    "/api/v1/segments/SEG-2/allocations",
                    json=self._manual_payload(today, 8),
                    headers={"Idempotency-Key": "seg2-reduce-first"},
                )
                self.assertEqual(first.status_code, 201, first.text)
                second = client.post(
                    "/api/v1/segments/SEG-2/allocations",
                    json=self._manual_payload(today, 4, "INCREASE_PLANNED"),
                    headers={"Idempotency-Key": "seg2-reduce-second"},
                )
                self.assertEqual(second.status_code, 201, second.text)

                blocked = client.patch(
                    "/api/v1/segments/SEG-2",
                    json={"planned_hours": 10},
                )
                self.assertEqual(blocked.status_code, 422, blocked.text)
                error = blocked.json()["error"]
                self.assertEqual(error["code"], "segment_overallocation_choice_required")
                self.assertEqual(error["context"]["locked_hours"], 12.0)
                self.assertEqual(error["context"]["excess_hours"], 2.0)

                explicit = client.patch(
                    "/api/v1/segments/SEG-2",
                    json={
                        "planned_hours": 10,
                        "allow_locked_overallocation": True,
                    },
                )
                self.assertEqual(explicit.status_code, 200, explicit.text)
                segment = client.get("/api/v1/segments/SEG-2").json()
                self.assertEqual(segment["planned_hours"], 10.0)
                self.assertEqual(segment["locked_hours"], 12.0)
                self.assertEqual(segment["overallocated_hours"], 2.0)

                regularized = client.patch(
                    "/api/v1/segments/SEG-2",
                    json={"planned_hours": 12},
                )
                self.assertEqual(regularized.status_code, 200, regularized.text)
                segment = client.get("/api/v1/segments/SEG-2").json()
                self.assertEqual(segment["overallocated_hours"], 0.0)

                actions = [
                    row["action"]
                    for row in client.get("/api/v1/segments/SEG-2/history").json()
                ]
                self.assertIn("Dérogation surallocation manuelle", actions)
                self.assertIn("Régularisation surallocation manuelle", actions)

            engine = create_sql_engine(database_url)
            factory = create_session_factory(engine)
            with factory() as session:
                audit = session.scalars(
                    select(PlanningChangeHistory).where(
                        PlanningChangeHistory.entity_reference == "SEG-2"
                    )
                ).all()
                self.assertTrue(any(row.actor_name == "coord-surallocation" for row in audit))
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
