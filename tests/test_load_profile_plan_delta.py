from __future__ import annotations

from datetime import date
from decimal import Decimal
import unittest

from app.infrastructure.sql import (
    Base,
    Project,
    ResourceRequirement,
    SqlPlannerQueryRepositoryWithLoadProfiles,
    WorkforceRequest,
    create_session_factory,
    create_sql_engine,
    transactional_session,
)
from app.infrastructure.sql.planning_repository import SqlPlanningReadRepository
from app.domain.planning_projection import project_planning_snapshot


class LoadProfilePlanDeltaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_sql_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.factory = create_session_factory(self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_existing_profile_is_projected_into_proposed_segment_rows(self) -> None:
        with transactional_session(self.factory) as session:
            session.add(Project(id="P1", number="P-14", name="Projet profil"))
            session.flush()
            session.add(
                WorkforceRequest(
                    id="D1",
                    legacy_demand_number="DEM-14",
                    project_id="P1",
                    desired_start=date(2026, 9, 14),
                    desired_end=date(2026, 9, 18),
                    estimated_hours=Decimal("24"),
                    resource_count=1,
                    status="Soumise",
                )
            )
            session.flush()
            session.add(
                ResourceRequirement(
                    id="S1",
                    legacy_segment_id="SEG-14",
                    project_id="P1",
                    workforce_request_id="D1",
                    start_date=date(2026, 9, 14),
                    end_date=date(2026, 9, 18),
                    planned_hours=Decimal("24"),
                    planning_type="Flexible",
                    load_profile="BACK_LOADED",
                    status="À assigner",
                )
            )
            session.flush()

            queries = SqlPlannerQueryRepositoryWithLoadProfiles(session)
            request = session.get(WorkforceRequest, "D1")
            current = [session.get(ResourceRequirement, "S1")]
            snapshot = SqlPlanningReadRepository(session).capture()
            proposed = queries._proposed_segments(request, current, snapshot)
            self.assertIsNotNone(proposed)
            self.assertEqual(proposed[0]["ProfilCharge"], "BACK_LOADED")

            projected = project_planning_snapshot(
                type(snapshot).capture(
                    segments=proposed,
                    demands=snapshot.demands,
                    allocations=snapshot.allocations,
                    availability=snapshot.availability,
                    technicians=snapshot.technicians,
                )
            )
            # No schedulable resource is configured in this tiny fixture, so there is
            # intentionally no SegmentInput; the row itself is the contract under test.
            self.assertEqual(projected.unsupported_segment_ids, ())


if __name__ == "__main__":
    unittest.main()
