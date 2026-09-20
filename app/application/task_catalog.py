from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .errors import ApplicationValidationError


@dataclass(frozen=True, slots=True)
class TaskCatalogItem:
    """Transport-neutral ERP task reference.

    The ERP export does not expose a globally unique task row identifier. The stable
    business identity is therefore the pair (project_number, code). A future Acumatica
    source can feed this same contract without changing consumers.
    """

    project_number: str
    code: str
    label: str
    status: str = "Actif"
    active: bool = True
    billing_rule: str | None = None
    allocation_rule: str | None = None
    completion_percent: float | None = None
    erp_created_at: datetime | None = None
    branch: str | None = None
    approver_name: str | None = None
    cv_enabled: bool | None = None
    time_entry_enabled: bool | None = None
    expenses_enabled: bool | None = None
    id: str | None = None
    operational_responsible_contact_id: str | None = None
    coordinator_contact_id: str | None = None

    @property
    def external_key(self) -> tuple[str, str]:
        return (self.project_number, self.code)


class TaskCatalogSourcePort(Protocol):
    """Read-only source of a task-catalog snapshot."""

    def list_tasks(self) -> Sequence[TaskCatalogItem]: ...


class TaskCatalogRepositoryPort(Protocol):
    """Persistence/search contract independent from SQLite, SQL Server and Acumatica."""

    def upsert(self, item: TaskCatalogItem) -> str: ...

    def search(
        self,
        *,
        project_number: str | None = None,
        query: str | None = None,
        active_only: bool = True,
        limit: int = 200,
    ) -> Sequence[TaskCatalogItem]: ...


@dataclass(frozen=True, slots=True)
class TaskCatalogSyncResult:
    received: int
    created: int
    updated: int
    unchanged: int
    deactivated: int

    def to_dict(self) -> dict[str, int]:
        return {
            "received": self.received,
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "deactivated": self.deactivated,
        }


class TaskCatalogSyncService:
    """Idempotently synchronize one source snapshot into the durable catalog."""

    def __init__(
        self,
        source: TaskCatalogSourcePort,
        repository: TaskCatalogRepositoryPort,
    ) -> None:
        self._source = source
        self._repository = repository

    def synchronize(self) -> TaskCatalogSyncResult:
        rows = tuple(self._source.list_tasks())
        seen: set[tuple[str, str]] = set()
        counts = {
            "created": 0,
            "updated": 0,
            "unchanged": 0,
            "deactivated": 0,
        }

        for item in rows:
            project_number = str(item.project_number or "").strip()
            code = str(item.code or "").strip()
            label = str(item.label or "").strip()
            if not project_number or not code or not label:
                raise ApplicationValidationError(
                    "Une tâche ERP doit avoir un projet, un code et un libellé.",
                    code="task_catalog_item_invalid",
                    context={
                        "project_number": project_number or None,
                        "task_code": code or None,
                    },
                )
            key = (project_number, code)
            if key in seen:
                raise ApplicationValidationError(
                    "La même tâche ERP apparaît plus d'une fois pour un projet.",
                    code="task_catalog_duplicate_key",
                    context={"project_number": project_number, "task_code": code},
                )
            seen.add(key)
            action = self._repository.upsert(item)
            if action not in counts:
                raise RuntimeError(f"Unsupported task catalog synchronization action: {action}")
            counts[action] += 1

        return TaskCatalogSyncResult(
            received=len(rows),
            created=counts["created"],
            updated=counts["updated"],
            unchanged=counts["unchanged"],
            deactivated=counts["deactivated"],
        )
