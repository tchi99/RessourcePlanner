from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.application.errors import ApplicationConflictError
from app.infrastructure.sql import (
    Base,
    PlanningMutationState,
    SqlPlanningCommandAdapter,
    SqlPlanningMutationVersionRepository,
    create_session_factory,
    create_sql_engine,
)


class SqlPlanningMutationVersionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        database_path = Path(self.directory.name) / "planning-version.db"
        self.engine = create_sql_engine(
            f"sqlite+pysqlite:///{database_path.as_posix()}"
        )
        Base.metadata.create_all(self.engine)
        self.factory = create_session_factory(self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.directory.cleanup()

    def test_current_version_defaults_to_one_without_mutating_read(self) -> None:
        with self.factory() as session:
            repository = SqlPlanningMutationVersionRepository(session)
            self.assertEqual(repository.current_version(), 1)
            self.assertIsNone(session.get(PlanningMutationState, 1))

    def test_reentrant_guard_advances_once_per_transaction(self) -> None:
        with self.factory() as session:
            with session.begin():
                repository = SqlPlanningMutationVersionRepository(session)
                self.assertEqual(repository.acquire(), 2)
                self.assertEqual(repository.acquire(), 2)
                self.assertEqual(repository.current_version(), 2)

        with self.factory() as session:
            with session.begin():
                repository = SqlPlanningMutationVersionRepository(session)
                self.assertEqual(repository.acquire(), 3)

    def test_stale_expected_version_conflicts_across_two_sessions(self) -> None:
        first = self.factory()
        second = self.factory()
        try:
            with first.begin():
                first_repository = SqlPlanningMutationVersionRepository(first)
                self.assertEqual(first_repository.acquire(expected_version=1), 2)

            with second.begin():
                second_repository = SqlPlanningMutationVersionRepository(second)
                with self.assertRaises(ApplicationConflictError) as caught:
                    second_repository.acquire(expected_version=1)

                self.assertEqual(caught.exception.code, "planning_version_conflict")
                self.assertEqual(
                    caught.exception.context["expected_planning_version"],
                    1,
                )
                self.assertEqual(
                    caught.exception.context["current_planning_version"],
                    2,
                )
        finally:
            first.close()
            second.close()

    def test_guard_rollback_restores_revision(self) -> None:
        session = self.factory()
        try:
            transaction = session.begin()
            repository = SqlPlanningMutationVersionRepository(session)
            self.assertEqual(repository.acquire(), 2)
            transaction.rollback()
        finally:
            session.close()

        with self.factory() as session:
            self.assertEqual(
                SqlPlanningMutationVersionRepository(session).current_version(),
                1,
            )

    def test_guarded_rebuild_does_not_double_increment(self) -> None:
        with self.factory() as session:
            with session.begin():
                repository = SqlPlanningMutationVersionRepository(session)
                self.assertEqual(repository.acquire(), 2)
                summary = SqlPlanningCommandAdapter(
                    session,
                    versioning=repository,
                ).rebuild()
                self.assertEqual(repository.current_version(), 2)
                self.assertEqual(summary["planning_engine"], "pure")


if __name__ == "__main__":
    unittest.main()
