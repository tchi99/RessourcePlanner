from __future__ import annotations

from datetime import date, time
from decimal import Decimal
import unittest

from sqlalchemy import func, select

from app.domain.plan_comparison import AllocationDifference
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
from app.infrastructure.sql.plan_delta_query_repository import (
    SqlPlannerQueryRepositoryWithPlanDelta,
    _delta_items,
)


D1 = date(2026, 9, 14)
D2 = date(2026, 9, 15)


class PlanDeltaGroupingTests(unittest.TestCase):
    def test_same_segment_same_hours_on_another_day_is_one_move(self) -> None:
        rows = (
            AllocationDifference(
                segment_id="SEG-1",
                resource_id="Alice",
                day=D1,
                allocation_type="Auto",
                locked=False,
                outside_schedule=False,
                legacy_hours=8.0,
                shadow_hours=0.0,
            ),
            AllocationDifference(
                segment_id="SEG-1",
                resource_id="Alice",
                day=D2,
                allocation_type="Auto",
                locked=False,
                outside_schedule=False,
                legacy_hours=0.0,
                shadow_hours=8.0,
            ),
        )

        items = _delta_items(rows)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].change, "MOVE")
        self.assertEqual(items[0].current_date, D1)
        self.assertEqual(items[0].proposed_date, D2)
        self.assertEqual(items[0].current_hours, 8.0)
        self.assertEqual(items[0].proposed_hours, 8.0)


class SqlPlanDeltaPreviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_sql_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.factory = create_session_factory(self.engine)
        with transactional_session(self.factory) as session:
            session.add(Project(id="P1", number="P-1", name="Projet delta"))
            session.add(Resource(id="R1", name="Alice", active=True))
            session.flush()
            session.add(
                ResourceAvailabilityRule(
                    id="SCH-R1",
                    resource_id="R1",
                    availability_type="Horaire standard",
                    start_date=D1,
                    end_date=D2,
                    weekdays="Lun,Mar",
                    start_time=time(8, 0),
                    end_time=time(16, 0),
                    active=True,
                )
            )

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_submitted_demand_without_approved_plan_returns_explicit_state(self) -> None:
        with transactional_session(self.factory) as session:
            session.add(
                WorkforceRequest(
                    id="D-NO-PLAN",
                    legacy_demand_number="DEM-NO-PLAN",
                    project_id="P1",
                    desired_start=D2,
                    desired_end=D2,
                    estimated_hours=Decimal("8"),
                    resource_count=1,
                    proposed_resource_id="R1",
                    status="Soumise",
                )
            )
            session.flush()

            result = SqlPlannerQueryRepositoryWithPlanDelta(session).demand_plan_delta(
                "DEM-NO-PLAN"
            )

            self.assertIsNotNone(result)
            assert result is not None
            self.assertFalse(result.available)
            self.assertEqual(result.reason, "NO_CURRENT_PLAN")
            self.assertFalse(result.has_changes)

    def test_preview_detects_move_and_does_not_mutate_current_plan(self) -> None:
        with transactional_session(self.factory) as session:
            session.add(
                WorkforceRequest(
                    id="D1",
                    legacy_demand_number="DEM-1",
                    project_id="P1",
                    desired_start=D2,
                    desired_end=D2,
                    estimated_hours=Decimal("8"),
                    resource_count=1,
                    proposed_resource_id="R1",
                    status="Soumise",
                    description="Besoin déplacé au mardi",
                )
            )
            session.add(
                ResourceRequirement(
                    id="REQ1",
                    legacy_segment_id="SEG-1",
                    project_id="P1",
                    workforce_request_id="D1",
                    assigned_resource_id="R1",
                    start_date=D1,
                    end_date=D1,
                    planned_hours=Decimal("8"),
                    status="Planifié",
                    planning_type="Flexible",
                    origin="REQUEST",
                )
            )
            session.flush()
            session.add(
                Shift(
                    id="SHIFT1",
                    legacy_allocation_id="AUTO-1",
                    resource_requirement_id="REQ1",
                    resource_id="R1",
                    work_date=D1,
                    hours=Decimal("8"),
                    allocation_type="Auto",
                    source="AUTO",
                    locked=False,
                )
            )
            session.flush()

            before_requirements = session.scalar(
                select(func.count()).select_from(ResourceRequirement)
            )
            before_shifts = session.scalar(select(func.count()).select_from(Shift))

            result = SqlPlannerQueryRepositoryWithPlanDelta(session).demand_plan_delta("DEM-1")

            self.assertIsNotNone(result)
            assert result is not None
            self.assertTrue(result.available)
            self.assertTrue(result.has_changes)
            self.assertEqual(result.move_count, 1)
            self.assertEqual(result.add_count, 0)
            self.assertEqual(result.modify_count, 0)
            self.assertEqual(result.cancel_count, 0)
            self.assertEqual(result.current_hours, 8.0)
            self.assertEqual(result.proposed_hours, 8.0)
            self.assertEqual(result.net_hours, 0.0)
            self.assertEqual(len(result.items), 1)
            self.assertEqual(result.items[0].change, "MOVE")
            self.assertEqual(result.items[0].segment_id, "SEG-1")
            self.assertEqual(result.items[0].current_date, D1)
            self.assertEqual(result.items[0].proposed_date, D2)

            self.assertEqual(
                session.scalar(select(func.count()).select_from(ResourceRequirement)),
                before_requirements,
            )
            self.assertEqual(
                session.scalar(select(func.count()).select_from(Shift)),
                before_shifts,
            )
            current_requirement = session.get(ResourceRequirement, "REQ1")
            current_shift = session.get(Shift, "SHIFT1")
            assert current_requirement is not None and current_shift is not None
            self.assertEqual(current_requirement.start_date, D1)
            self.assertEqual(current_requirement.end_date, D1)
            self.assertEqual(current_shift.work_date, D1)


if __name__ == "__main__":
    unittest.main()
