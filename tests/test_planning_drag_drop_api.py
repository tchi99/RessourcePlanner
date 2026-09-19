from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from app.infrastructure.sql import (
    Base,
    Project,
    Resource,
    ResourceAvailabilityRule,
    ResourceRequirement,
    Shift,
    create_session_factory,
    create_sql_engine,
)
from app.server import create_api_app


class PlanningDragDropApiTests(unittest.TestCase):
    def _database(self, directory: str) -> str:
        path = Path(directory) / "planning-drag-drop.db"
        url = f"sqlite+pysqlite:///{path.as_posix()}"
        engine = create_sql_engine(url)
        Base.metadata.create_all(engine)
        factory = create_session_factory(engine)

        with factory.begin() as session:
            project = Project(
                id="P-275",
                number="P-275",
                name="Projet drag drop",
                status="active",
            )
            alice = Resource(
                id="R-ALICE-275",
                name="Alice DnD",
                resource_class="Programmation",
                active=True,
                sort_order=10,
            )
            bob = Resource(
                id="R-BOB-275",
                name="Bob DnD",
                resource_class="Programmation",
                active=True,
                sort_order=20,
            )
            session.add_all([project, alice, bob])
            session.flush()

            for resource, suffix in ((alice, "ALICE"), (bob, "BOB")):
                session.add(
                    ResourceAvailabilityRule(
                        id=f"SCH-{suffix}-275",
                        resource_id=resource.id,
                        availability_type="Horaire standard",
                        start_date=date(2026, 1, 1),
                        end_date=date(2026, 12, 31),
                        weekdays="Lun,Mar,Mer,Jeu,Ven",
                        start_time=time(7, 0),
                        end_time=time(15, 0),
                        active=True,
                    )
                )
            session.add(
                ResourceAvailabilityRule(
                    id="VAC-BOB-275",
                    resource_id=bob.id,
                    availability_type="Vacances",
                    start_date=date(2026, 9, 23),
                    end_date=date(2026, 9, 23),
                    active=True,
                )
            )

            requirement = ResourceRequirement(
                id="REQ-275",
                legacy_segment_id="SEG-275",
                project_id=project.id,
                assigned_resource_id=alice.id,
                start_date=date(2026, 9, 21),
                end_date=date(2026, 9, 25),
                planned_hours=Decimal("8"),
                status="Planifié",
                confirmation="Confirmée",
                origin="AD_HOC",
            )
            session.add(requirement)
            session.flush()
            session.add(
                Shift(
                    id="SHIFT-275",
                    resource_requirement_id=requirement.id,
                    resource_id=alice.id,
                    work_date=date(2026, 9, 21),
                    hours=Decimal("8"),
                    allocation_type="Flexible",
                    source="AUTO",
                    locked=False,
                    outside_standard_hours=False,
                    note="Quart généré",
                )
            )

        engine.dispose()
        return url

    def test_move_contract_reassigns_day_and_locks_explicit_decision(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(self._database(directory), actor_name="Coordonnateur DnD")
            with TestClient(app) as client:
                response = client.post(
                    "/api/v1/allocations/SHIFT-275/move",
                    json={"technician": "Bob DnD", "day": "2026-09-22"},
                )
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["action"], "moved")

                shifts = client.get(
                    "/api/v1/shifts",
                    params={"start": "2026-09-21", "end": "2026-09-27"},
                ).json()
                history = client.get("/api/v1/shifts/SHIFT-275/history").json()

            moved = next(row for row in shifts if row["allocation_id"] == "SHIFT-275")
            self.assertEqual(moved["resource_name"], "Bob DnD")
            self.assertEqual(moved["work_date"], "2026-09-22")
            self.assertEqual(moved["hours"], 8.0)
            self.assertEqual(moved["source"], "MANUAL")
            self.assertTrue(moved["locked"])
            self.assertFalse(moved["outside_standard_hours"])
            self.assertEqual(moved["note"], "Quart généré")
            self.assertTrue(any(row["action"] == "Déplacement quart" for row in history))

    def test_quick_shift_move_cannot_leave_its_single_day_segment(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(self._database(directory))
            with TestClient(app) as client:
                created = client.post(
                    "/api/v1/quick-shifts",
                    json={
                        "project_number": "P-275",
                        "project_name": "Projet drag drop",
                        "technician": "Alice DnD",
                        "day": "2026-09-24",
                        "hours": 2,
                        "outside_standard_hours": False,
                        "note": "Quick Shift fenêtre #275",
                        "description": "Quick Shift fenêtre",
                        "confirmation": "Confirmée",
                    },
                )
                self.assertEqual(created.status_code, 201, created.text)
                allocation_id = created.json()["allocation_id"]
                segment_id = created.json()["segment_id"]

                segment = client.get(f"/api/v1/segments/{segment_id}").json()
                self.assertEqual(segment["start_date"], "2026-09-24")
                self.assertEqual(segment["end_date"], "2026-09-24")

                response = client.post(
                    f"/api/v1/allocations/{allocation_id}/move",
                    json={"technician": "Bob DnD", "day": "2026-09-25"},
                )
                self.assertEqual(response.status_code, 422, response.text)
                self.assertIn("fenêtre du segment", response.json()["error"]["message"])

                shifts = client.get(
                    "/api/v1/shifts",
                    params={"start": "2026-09-21", "end": "2026-09-27"},
                ).json()

            original = next(row for row in shifts if row["allocation_id"] == allocation_id)
            self.assertEqual(original["resource_name"], "Alice DnD")
            self.assertEqual(original["work_date"], "2026-09-24")
            self.assertTrue(original["locked"])

    def test_move_rejected_outside_standard_schedule_rolls_back(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(self._database(directory))
            with TestClient(app) as client:
                response = client.post(
                    "/api/v1/allocations/SHIFT-275/move",
                    json={"technician": "Bob DnD", "day": "2026-09-23"},
                )
                self.assertEqual(response.status_code, 422, response.text)
                self.assertIn("horaire standard", response.json()["error"]["message"])

                shifts = client.get(
                    "/api/v1/shifts",
                    params={"start": "2026-09-21", "end": "2026-09-27"},
                ).json()

            original = next(row for row in shifts if row["allocation_id"] == "SHIFT-275")
            self.assertEqual(original["resource_name"], "Alice DnD")
            self.assertEqual(original["work_date"], "2026-09-21")
            self.assertEqual(original["source"], "AUTO")
            self.assertFalse(original["locked"])


if __name__ == "__main__":
    unittest.main()
