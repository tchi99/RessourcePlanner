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


class PlanningCapacityGridApiTests(unittest.TestCase):
    def _database(self, directory: str) -> str:
        path = Path(directory) / "planning-capacity-grid.db"
        url = f"sqlite+pysqlite:///{path.as_posix()}"
        engine = create_sql_engine(url)
        Base.metadata.create_all(engine)
        factory = create_session_factory(engine)

        with factory.begin() as session:
            project = Project(
                id="P-282",
                number="P-282",
                name="Projet capacité",
                status="active",
            )
            resource = Resource(
                id="R-ALICE",
                name="Alice",
                resource_class="Programmation",
                active=True,
                sort_order=10,
            )
            session.add_all([project, resource])
            session.flush()

            session.add_all(
                [
                    ResourceAvailabilityRule(
                        id="SCH-ALICE",
                        resource_id=resource.id,
                        availability_type="Horaire standard",
                        start_date=date(2026, 1, 1),
                        end_date=date(2026, 12, 31),
                        weekdays="Lun,Mar,Mer,Jeu,Ven",
                        start_time=time(7, 0),
                        end_time=time(15, 0),
                        active=True,
                    ),
                    ResourceAvailabilityRule(
                        id="VAC-ALICE",
                        resource_id=resource.id,
                        availability_type="Vacances",
                        start_date=date(2026, 9, 22),
                        end_date=date(2026, 9, 22),
                        active=True,
                    ),
                    ResourceAvailabilityRule(
                        id="HOL-ALL",
                        resource_id=None,
                        availability_type="Jour férié",
                        start_date=date(2026, 9, 23),
                        end_date=date(2026, 9, 23),
                        active=True,
                    ),
                ]
            )

            requirement = ResourceRequirement(
                id="REQ-282",
                legacy_segment_id="SEG-282",
                project_id=project.id,
                assigned_resource_id=resource.id,
                start_date=date(2026, 9, 21),
                end_date=date(2026, 10, 2),
                planned_hours=Decimal("30"),
                status="Planifié",
                confirmation="Confirmée",
                origin="AD_HOC",
            )
            session.add(requirement)
            session.flush()
            session.add_all(
                [
                    Shift(
                        id="SHIFT-MON",
                        resource_requirement_id=requirement.id,
                        resource_id=resource.id,
                        work_date=date(2026, 9, 21),
                        hours=Decimal("8"),
                        source="AUTO",
                        locked=False,
                        outside_standard_hours=False,
                    ),
                    Shift(
                        id="SHIFT-THU",
                        resource_requirement_id=requirement.id,
                        resource_id=resource.id,
                        work_date=date(2026, 9, 24),
                        hours=Decimal("6"),
                        source="AUTO",
                        locked=False,
                        outside_standard_hours=False,
                        confirmation="Tentative",
                    ),
                    Shift(
                        id="SHIFT-FRI",
                        resource_requirement_id=requirement.id,
                        resource_id=resource.id,
                        work_date=date(2026, 9, 25),
                        hours=Decimal("4"),
                        source="MANUAL",
                        locked=True,
                        outside_standard_hours=True,
                    ),
                    # Outside the displayed week on purpose. Segment diagnostics must
                    # use the full segment allocation, not only visible shifts.
                    Shift(
                        id="SHIFT-NEXT-WEEK",
                        resource_requirement_id=requirement.id,
                        resource_id=resource.id,
                        work_date=date(2026, 9, 28),
                        hours=Decimal("2"),
                        source="AUTO",
                        locked=False,
                        outside_standard_hours=False,
                    ),
                ]
            )

        engine.dispose()
        return url

    def test_capacity_grid_explains_daily_availability_and_weekly_capacity(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(self._database(directory))
            with TestClient(app) as client:
                response = client.get(
                    "/api/v1/planning/capacity-grid",
                    params={"start": "2026-09-21", "end": "2026-09-27"},
                )

            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertEqual(payload["start"], "2026-09-21")
            self.assertEqual(payload["end"], "2026-09-27")
            self.assertEqual(len(payload["resources"]), 1)

            alice = payload["resources"][0]
            self.assertEqual(alice["resource_name"], "Alice")
            self.assertEqual(alice["capacity_hours"], 24.0)
            self.assertEqual(alice["confirmed_hours"], 8.0)
            self.assertEqual(alice["tentative_hours"], 6.0)
            self.assertEqual(alice["outside_standard_hours"], 4.0)
            self.assertEqual(alice["prudent_free"], 10.0)
            self.assertFalse(alice["overloaded"])

            days = {row["day"]: row for row in alice["days"]}
            self.assertEqual(days["2026-09-21"]["capacity_hours"], 8.0)
            self.assertEqual(days["2026-09-21"]["confirmed_hours"], 8.0)
            self.assertTrue(days["2026-09-21"]["available"])

            self.assertEqual(days["2026-09-22"]["capacity_hours"], 0.0)
            self.assertFalse(days["2026-09-22"]["available"])
            self.assertEqual(days["2026-09-22"]["reason"], "Vacances")

            self.assertEqual(days["2026-09-23"]["capacity_hours"], 0.0)
            self.assertFalse(days["2026-09-23"]["available"])
            self.assertEqual(days["2026-09-23"]["reason"], "Jour férié")

            self.assertEqual(days["2026-09-24"]["tentative_hours"], 6.0)
            self.assertEqual(days["2026-09-25"]["outside_standard_hours"], 4.0)

    def test_segment_diagnostic_uses_full_segment_allocation(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(self._database(directory))
            with TestClient(app) as client:
                response = client.get(
                    "/api/v1/planning/capacity-grid",
                    params={"start": "2026-09-21", "end": "2026-09-27"},
                )

            self.assertEqual(response.status_code, 200, response.text)
            diagnostics = response.json()["segment_diagnostics"]
            self.assertEqual(len(diagnostics), 1)
            row = diagnostics[0]
            self.assertEqual(row["segment_id"], "SEG-282")
            self.assertEqual(row["planned_hours"], 30.0)
            self.assertEqual(row["allocated_hours"], 20.0)
            self.assertEqual(row["outside_standard_hours"], 4.0)
            self.assertEqual(row["unplaced_hours"], 10.0)
            self.assertTrue(row["requires_outside_standard_hours"])


if __name__ == "__main__":
    unittest.main()
