from __future__ import annotations

from datetime import date, timedelta
import unittest

from app.infrastructure.sql import Base, create_session_factory, create_sql_engine
from app.infrastructure.sql.web_query_repository import SqlPlannerQueryRepositoryWeb
from tools.seed_demo_data import seed_demo_database, seed_demo_session


class DemoSeedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_sql_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.factory = create_session_factory(self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_seed_populates_current_week_and_is_reentrant(self) -> None:
        today = date(2026, 9, 12)
        monday = date(2026, 9, 7)

        with self.factory.begin() as session:
            first = seed_demo_session(session, today=today)
        with self.factory.begin() as session:
            second = seed_demo_session(session, today=today)

        self.assertEqual(first, second)
        self.assertEqual(second.week_start, monday)
        self.assertEqual(second.projects, 3)
        self.assertEqual(second.resources, 6)
        self.assertEqual(second.work_packages, 4)
        self.assertEqual(second.demands, 4)
        self.assertEqual(second.requirements, 3)
        self.assertEqual(second.shifts, 5)
        self.assertEqual(second.periods, 3)

        with self.factory() as session:
            queries = SqlPlannerQueryRepositoryWeb(session)
            snapshot = queries.planning_snapshot(
                start=monday,
                end=monday + timedelta(days=6),
            )
            work_packages = queries.list_work_packages(active_only=True)

        self.assertEqual(len(snapshot.resources), 6)
        self.assertEqual(len(snapshot.shifts), 5)
        self.assertEqual(len(work_packages), 4)
        self.assertIn("DEMO-DMO-001", {row.number for row in snapshot.demands})
        pending = {
            row.demand_number: row
            for row in snapshot.pending_loads
        }
        self.assertIn("DEMO-DMO-002", pending)
        self.assertEqual(pending["DEMO-DMO-002"].window_hours, 12.0)
        self.assertEqual(snapshot.firm_hours, 30.0)
        self.assertEqual(snapshot.potential_hours, 16.0)

    def test_database_entrypoint_refuses_non_sqlite(self) -> None:
        with self.assertRaisesRegex(ValueError, "limité à SQLite"):
            seed_demo_database("mssql+pyodbc://server/database")


if __name__ == "__main__":
    unittest.main()
