from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True, slots=True)
class ExternalProjectRecord:
    """Transport-neutral project snapshot supplied by an ERP integration."""

    external_id: str
    number: str
    name: str
    client: str | None = None
    project_manager_external_id: str | None = None
    project_manager_name: str | None = None
    status: str = "active"


class ProjectSourcePort(Protocol):
    """Read-only source of ERP projects.

    The source is deliberately independent from SQL and HTTP so Acumatica can be
    replaced or simulated without changing application rules.
    """

    def list_projects(self) -> Sequence[ExternalProjectRecord]: ...


class ProjectSyncRepositoryPort(Protocol):
    """Persistence boundary for one external project snapshot."""

    def upsert_external_project(self, project: ExternalProjectRecord) -> str: ...


@dataclass(frozen=True, slots=True)
class ProjectSyncResult:
    received: int
    created: int
    updated: int
    unchanged: int


class ProjectSyncService:
    """Synchronize ERP project snapshots without deleting records missing from a pull."""

    def __init__(
        self,
        source: ProjectSourcePort,
        repository: ProjectSyncRepositoryPort,
    ) -> None:
        self._source = source
        self._repository = repository

    def synchronize(self) -> ProjectSyncResult:
        projects = tuple(self._source.list_projects())
        created = 0
        updated = 0
        unchanged = 0

        for project in projects:
            action = self._repository.upsert_external_project(project)
            if action == "created":
                created += 1
            elif action == "updated":
                updated += 1
            elif action == "unchanged":
                unchanged += 1
            else:
                raise ValueError(f"Action de synchronisation projet inconnue: {action}")

        return ProjectSyncResult(
            received=len(projects),
            created=created,
            updated=updated,
            unchanged=unchanged,
        )
