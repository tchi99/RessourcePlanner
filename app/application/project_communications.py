from __future__ import annotations

from datetime import date, timedelta
from typing import Protocol, Sequence

from ..domain.project_communication import (
    ProjectCommunicationAssignment,
    ProjectCommunicationProjection,
    build_project_communication_projection,
)
from ..domain.project_communication_messages import (
    ProjectCommunicationMessageBatch,
    build_project_confirmation_batch,
)
from .errors import call_application_port


class ProjectCommunicationRepositoryPort(Protocol):
    def list_assignments(
        self,
        *,
        week_start: date,
        week_end: date,
    ) -> Sequence[ProjectCommunicationAssignment]: ...


class ProjectCommunicationService:
    """Authoritative project-centric communication read model for #290."""

    def __init__(self, repository: ProjectCommunicationRepositoryPort) -> None:
        self._repository = repository

    @staticmethod
    def _normalize_week_start(value: date) -> date:
        return value - timedelta(days=value.weekday())

    def project_projection(self, *, week_start: date) -> ProjectCommunicationProjection:
        week = self._normalize_week_start(week_start)
        week_end = week + timedelta(days=6)
        assignments = call_application_port(
            lambda: self._repository.list_assignments(
                week_start=week,
                week_end=week_end,
            ),
            code_prefix="project_communication_read",
            context={"week_start": week.isoformat()},
        )
        return build_project_communication_projection(
            week_start=week,
            week_end=week_end,
            assignments=tuple(assignments),
        )

    def project_preview(
        self,
        *,
        week_start: date,
    ) -> ProjectCommunicationMessageBatch:
        return build_project_confirmation_batch(
            self.project_projection(week_start=week_start)
        )
