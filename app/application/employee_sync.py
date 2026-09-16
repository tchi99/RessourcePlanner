from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True, slots=True)
class ExternalEmployeeRecord:
    """Minimal ERP-owned employee data safe to synchronize before Acumatica mapping is known."""

    external_id: str
    display_name: str
    email: str | None = None
    active: bool = True


class EmployeeSourcePort(Protocol):
    def list_employees(self) -> Sequence[ExternalEmployeeRecord]: ...


class EmployeeSyncRepositoryPort(Protocol):
    def upsert_external_employee(self, employee: ExternalEmployeeRecord) -> str: ...


@dataclass(frozen=True, slots=True)
class EmployeeSyncResult:
    received: int
    created: int
    updated: int
    unchanged: int


class EmployeeSyncService:
    """Synchronize ERP-owned employee attributes without touching planning-owned data."""

    def __init__(
        self,
        source: EmployeeSourcePort,
        repository: EmployeeSyncRepositoryPort,
    ) -> None:
        self._source = source
        self._repository = repository

    def synchronize(self) -> EmployeeSyncResult:
        employees = tuple(self._source.list_employees())
        created = 0
        updated = 0
        unchanged = 0
        for employee in employees:
            action = self._repository.upsert_external_employee(employee)
            if action == "created":
                created += 1
            elif action == "updated":
                updated += 1
            elif action == "unchanged":
                unchanged += 1
            else:
                raise ValueError(f"Action de synchronisation employé inconnue: {action}")
        return EmployeeSyncResult(
            received=len(employees),
            created=created,
            updated=updated,
            unchanged=unchanged,
        )
