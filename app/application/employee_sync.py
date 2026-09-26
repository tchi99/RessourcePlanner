from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from .errors import ApplicationError


@dataclass(frozen=True, slots=True)
class ExternalEmployeeRecord:
    """ERP-owned employee data mapped to a stable RessourcePlanner resource identity."""

    external_id: str
    display_name: str
    email: str | None = None
    erp_status: str | None = None
    erp_active: bool = False
    department_description: str | None = None
    department_code: str | None = None
    employee_class: str | None = None
    supervisor_external_id: str | None = None
    telephone: str | None = None
    branch_code: str | None = None
    contact_id: int | None = None


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
    errors: int


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
        errors = 0
        for employee in employees:
            try:
                action = self._repository.upsert_external_employee(employee)
            except ApplicationError:
                # One invalid/colliding ERP row must be visible in the reconciliation
                # report without preventing other independent rows from being applied.
                errors += 1
                continue
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
            errors=errors,
        )
