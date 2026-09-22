from __future__ import annotations

from sqlalchemy import CheckConstraint, Integer, select, text, update
from sqlalchemy.orm import Mapped, Session, mapped_column

from ...application.errors import ApplicationConflictError, ApplicationValidationError
from ...application.repository_ports import PlanningMutationVersionPort
from .base import Base


PLANNING_STATE_ID = 1
_SESSION_GUARD_KEY = "planning_mutation_version_guard"


class PlanningMutationState(Base):
    """Singleton revision protecting the current globally rebuilt planning state."""

    __tablename__ = "planning_mutation_state"
    __table_args__ = (
        CheckConstraint("id = 1", name="planning_mutation_state_singleton"),
        CheckConstraint("version >= 1", name="planning_mutation_state_version_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("1"),
    )


class SqlPlanningMutationVersionRepository(PlanningMutationVersionPort):
    """Acquire one global SQL CAS guard for the caller-owned transaction.

    The repository intentionally keeps the lock in the surrounding transaction.
    Re-entrant acquisitions in that same transaction are no-ops so a command can
    acquire before decision reads and later call a guarded rebuild without advancing
    the revision twice.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def _ensure_state(self) -> PlanningMutationState:
        state = self._session.get(PlanningMutationState, PLANNING_STATE_ID)
        if state is None:
            # Migrated databases are seeded by Alembic. This fallback keeps
            # Base.metadata.create_all() test/dev databases usable as well.
            state = PlanningMutationState(id=PLANNING_STATE_ID, version=1)
            self._session.add(state)
            self._session.flush()
        return state

    def current_version(self) -> int:
        return int(self._ensure_state().version)

    def acquire(self, expected_version: int | None = None) -> int:
        current_transaction = self._session.get_transaction()
        cached = self._session.info.get(_SESSION_GUARD_KEY)
        if (
            isinstance(cached, tuple)
            and len(cached) == 2
            and cached[0] is current_transaction
        ):
            acquired = int(cached[1])
            if expected_version is not None and int(expected_version) not in {
                acquired - 1,
                acquired,
            }:
                raise ApplicationConflictError(
                    "La version du planning a changé.",
                    code="planning_version_conflict",
                    context={
                        "expected_planning_version": int(expected_version),
                        "current_planning_version": acquired,
                    },
                )
            return acquired

        current = self.current_version()
        expected = current if expected_version is None else int(expected_version)
        if expected < 1:
            raise ApplicationValidationError(
                "La version attendue du planning doit être au moins 1.",
                code="planning_version_invalid",
                context={"expected_planning_version": expected},
            )

        result = self._session.execute(
            update(PlanningMutationState)
            .where(
                PlanningMutationState.id == PLANNING_STATE_ID,
                PlanningMutationState.version == expected,
            )
            .values(version=PlanningMutationState.version + 1)
        )
        if int(result.rowcount or 0) != 1:
            actual = self._session.scalar(
                select(PlanningMutationState.version).where(
                    PlanningMutationState.id == PLANNING_STATE_ID
                )
            )
            raise ApplicationConflictError(
                "Le planning a été modifié par une autre opération.",
                code="planning_version_conflict",
                context={
                    "expected_planning_version": expected,
                    "current_planning_version": int(actual or current),
                },
            )

        self._session.flush()
        acquired = expected + 1
        transaction = self._session.get_transaction()
        self._session.info[_SESSION_GUARD_KEY] = (transaction, acquired)
        return acquired
