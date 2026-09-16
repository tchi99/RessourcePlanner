from __future__ import annotations

from datetime import datetime, timezone
import unittest

from app.infrastructure.sql import Base, create_session_factory, create_sql_engine, transactional_session
from app.infrastructure.sql.models import Project, WorkforceRequest, WorkforceRequestHistory
from app.infrastructure.sql.web_query_repository import SqlPlannerQueryRepositoryWeb


class DemandHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_sql_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.factory = create_session_factory(self.engine)
        with transactional_session(self.factory) as session:
            session.add(Project(id="P1", number="P-1", name="Projet", status="Actif"))
            session.flush()
            session.add(
                WorkforceRequest(
                    id="WR1",
                    legacy_demand_number="DMO-2026-0001",
                    project_id="P1",
                    status="Soumise",
                    resource_count=1,
                )
            )
            session.flush()
            session.add_all(
                [
                    WorkforceRequestHistory(
                        id="H1",
                        workforce_request_id="WR1",
                        action="Création",
                        previous_status=None,
                        status="Brouillon",
                        comment="Demande créée",
                        actor_name="Alice",
                        occurred_at=datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc),
                    ),
                    WorkforceRequestHistory(
                        id="H2",
                        workforce_request_id="WR1",
                        action="Soumission",
                        previous_status="Brouillon",
                        status="Soumise",
                        details="Validation métier terminée",
                        actor_name="Bob",
                        occurred_at=datetime(2026, 9, 16, 13, 0, tzinfo=timezone.utc),
                    ),
                ]
            )

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_history_is_projected_newest_first_without_internal_ids(self) -> None:
        with self.factory() as session:
            rows = SqlPlannerQueryRepositoryWeb(session).list_demand_history("DMO-2026-0001")

        self.assertEqual([row.action for row in rows], ["Soumission", "Création"])
        self.assertEqual(rows[0].demand_number, "DMO-2026-0001")
        self.assertEqual(rows[0].previous_status, "Brouillon")
        self.assertEqual(rows[0].status, "Soumise")
        self.assertEqual(rows[0].details, "Validation métier terminée")
        self.assertEqual(rows[0].actor_name, "Bob")
        self.assertIsNone(rows[1].previous_status)

    def test_unknown_demand_history_is_empty_at_repository_boundary(self) -> None:
        with self.factory() as session:
            rows = SqlPlannerQueryRepositoryWeb(session).list_demand_history("UNKNOWN")
        self.assertEqual(rows, ())


if __name__ == "__main__":
    unittest.main()
