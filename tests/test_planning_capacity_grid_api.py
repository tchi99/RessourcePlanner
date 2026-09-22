from __future__ import annotations

from functools import partial

from datetime import date, time
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from app.domain.planning_engine import MISSING_ALLOCATION_TYPE
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


from tests.http_test_auth import TEST_ADMIN_AUTH_RESOLVER

create_api_app = partial(create_api_app, auth_resolver=TEST_ADMIN_AUTH_RESOLVER)

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
            bob = Resource(
                id="R-BOB",
                name="Bob",
                resource_class="Programmation",
                active=True,
                sort_order=20,
            )
            session.add_all([project, resource, bob])
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
                        id="SCH-BOB",
                        resource_id=bob.id,
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
            no_target = ResourceRequirement(
                id="REQ-NO-TARGET",
                legacy_segment_id="SEG-NO-TARGET",
                project_id=project.id,
                assigned_resource_id=None,
                start_date=date(2026, 9, 21),
                end_date=date(2026, 9, 25),
                planned_hours=Decimal("8"),
                status="À assigner",
                confirmation="Confirmée",
                origin="AD_HOC",
            )
            session.add_all([requirement, no_target])
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
                    Shift(
                        id="SHIFT-NO-TARGET-LOCK",
                        resource_requirement_id=no_target.id,
                        resource_id=bob.id,
                        work_date=date(2026, 9, 21),
                        hours=Decimal("4"),
                        allocation_type="Flexible",
                        source="MANUAL",
                        locked=True,
                        outside_standard_hours=False,
                    ),
                    Shift(
                        id="SHIFT-NO-TARGET-MISSING",
                        resource_requirement_id=no_target.id,
                        resource_id=bob.id,
                        work_date=date(2026, 9, 22),
                        hours=Decimal("4"),
                        allocation_type=MISSING_ALLOCATION_TYPE,
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
            self.assertEqual(len(payload["resources"]), 2)

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

            bob = next(row for row in payload["resources"] if row["resource_id"] == "R-BOB")
            self.assertEqual(bob["confirmed_hours"], 4.0)
            self.assertEqual(bob["tentative_hours"], 0.0)
            self.assertEqual(bob["outside_standard_hours"], 0.0)
            bob_days = {row["day"]: row for row in bob["days"]}
            self.assertEqual(bob_days["2026-09-21"]["confirmed_hours"], 4.0)
            self.assertEqual(bob_days["2026-09-22"]["total_hours"], 0.0)

    def test_segment_diagnostic_uses_full_segment_allocation(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(self._database(directory))
            with TestClient(app) as client:
                response = client.get(
                    "/api/v1/planning/capacity-grid",
                    params={"start": "2026-09-21", "end": "2026-09-27"},
                )

            self.assertEqual(response.status_code, 200, response.text)
            diagnostics = {
                row["segment_id"]: row
                for row in response.json()["segment_diagnostics"]
            }
            self.assertEqual(set(diagnostics), {"SEG-282", "SEG-NO-TARGET"})

            row = diagnostics["SEG-282"]
            self.assertEqual(row["planned_hours"], 30.0)
            self.assertEqual(row["allocated_hours"], 20.0)
            self.assertEqual(row["outside_standard_hours"], 4.0)
            self.assertEqual(row["unplaced_hours"], 10.0)
            self.assertEqual(row["automatic_target_resource_id"], "R-ALICE")
            self.assertEqual(row["automatic_target_resource_name"], "Alice")
            self.assertTrue(row["requires_outside_standard_hours"])

            no_target = diagnostics["SEG-NO-TARGET"]
            self.assertIsNone(no_target["automatic_target_resource_id"])
            self.assertIsNone(no_target["automatic_target_resource_name"])
            self.assertEqual(no_target["planned_hours"], 8.0)
            self.assertEqual(no_target["allocated_hours"], 4.0)
            self.assertEqual(no_target["unplaced_hours"], 4.0)


if __name__ == "__main__":
    unittest.main()
