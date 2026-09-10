from __future__ import annotations

from datetime import date
from decimal import Decimal
import unittest

from app.domain.confirmation import CONFIRMATION_CONFIRMED, CONFIRMATION_TENTATIVE
from app.domain.workload import (
    LOAD_FIRM,
    LOAD_POTENTIAL,
    WorkloadTotals,
    workload_kind,
)
from app.infrastructure.sql import (
    Base,
    Project,
    Resource,
    ResourceRequirement,
    Shift,
    SqlPlannerQueryRepository,
    create_session_factory,
    create_sql_engine,
    transactional_session,
)


class WorkloadPolicyTests(unittest.TestCase):
    def test_confirmation_maps_to_mutually_exclusive_load_kind(self) -> None:
        self.assertEqual(workload_kind(CONFIRMATION_CONFIRMED), LOAD_FIRM)
        self.assertEqual(workload_kind(CONFIRMATION_TENTATIVE), LOAD_POTENTIAL)
        self.assertEqual(workload_kind(None), LOAD_FIRM)

    def test_totals_never_double_count_one_hour_bucket(self) -> None:
        totals = WorkloadTotals()
        totals = totals.add(4, CONFIRMATION_CONFIRMED)
        totals = totals.add(3, CONFIRMATION_TENTATIVE)

        self.assertEqual(totals.firm_hours, 4.0)
        self.assertEqual(totals.potential_hours, 3.0)
        self.assertEqual(totals.exposure_hours, 7.0)


class SqlWorkloadProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_sql_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.factory = create_session_factory(self.engine)
        self.day = date(2026, 9, 14)

        with transactional_session(self.factory) as session:
            session.add(Project(id="P1", number="P-1", name="Projet", status="Actif"))
            session.add(Resource(id="R1", name="Alice", active=True, sort_order=1))
            session.flush()
            session.add(
                ResourceRequirement(
                    id="REQ1",
                    legacy_segment_id="SEG-1",
                    project_id="P1",
                    assigned_resource_id="R1",
                    start_date=self.day,
                    end_date=self.day,
                    planned_hours=Decimal("5"),
                    status="Planifié",
                    planning_type="Flexible",
                    priority="Normale",
                    confirmation=CONFIRMATION_TENTATIVE,
                    origin="QUICK_SHIFT",
                )
            )
            session.flush()
            session.add_all(
                [
                    Shift(
                        id="S1",
                        resource_requirement_id="REQ1",
                        resource_id="R1",
                        work_date=self.day,
                        hours=Decimal("3"),
                        source="AUTO",
                        locked=False,
                        confirmation=None,
                    ),
                    Shift(
                        id="S2",
                        resource_requirement_id="REQ1",
                        resource_id="R1",
                        work_date=self.day,
                        hours=Decimal("2"),
                        source="MANUAL",
                        locked=True,
                        confirmation=CONFIRMATION_CONFIRMED,
                    ),
                ]
            )

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_shift_read_models_expose_effective_load_kind(self) -> None:
        with self.factory() as session:
            shifts = SqlPlannerQueryRepository(session).list_shifts(
                start=self.day,
                end=self.day,
            )

        self.assertEqual([row.load_kind for row in shifts], [LOAD_POTENTIAL, LOAD_FIRM])
        self.assertEqual(
            [row.confirmation for row in shifts],
            [CONFIRMATION_TENTATIVE, CONFIRMATION_CONFIRMED],
        )

    def test_planning_snapshot_splits_firm_and_potential_hours(self) -> None:
        with self.factory() as session:
            snapshot = SqlPlannerQueryRepository(session).planning_snapshot(
                start=self.day,
                end=self.day,
            )

        self.assertEqual(snapshot.firm_hours, 2.0)
        self.assertEqual(snapshot.potential_hours, 3.0)
        self.assertEqual(snapshot.firm_hours + snapshot.potential_hours, 5.0)


if __name__ == "__main__":
    unittest.main()
