from __future__ import annotations

from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ...application.task_catalog import TaskCatalogItem, TaskCatalogRepositoryPort
from .models import TaskCatalogEntry


def _text(value: object) -> str:
    return str(value or "").strip()


def _optional_text(value: object) -> str | None:
    normalized = _text(value)
    return normalized or None


class SqlTaskCatalogRepository(TaskCatalogRepositoryPort):
    """SQL-backed durable task catalog keyed by project number + ERP task code."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _item(row: TaskCatalogEntry) -> TaskCatalogItem:
        return TaskCatalogItem(
            project_number=row.project_number,
            code=row.task_code,
            label=row.label,
            status=row.status,
            active=bool(row.active),
            billing_rule=row.billing_rule,
            allocation_rule=row.allocation_rule,
            completion_percent=(
                float(row.completion_percent)
                if row.completion_percent is not None
                else None
            ),
            erp_created_at=row.erp_created_at,
            branch=row.branch,
            approver_name=row.approver_name,
            cv_enabled=row.cv_enabled,
            time_entry_enabled=row.time_entry_enabled,
            expenses_enabled=row.expenses_enabled,
        )

    def upsert(self, item: TaskCatalogItem) -> str:
        project_number = _text(item.project_number)
        task_code = _text(item.code)
        row = self._session.scalar(
            select(TaskCatalogEntry).where(
                TaskCatalogEntry.project_number == project_number,
                TaskCatalogEntry.task_code == task_code,
            )
        )

        values = {
            "project_number": project_number,
            "task_code": task_code,
            "label": _text(item.label),
            "status": _text(item.status) or ("Actif" if item.active else "Inactif"),
            "active": bool(item.active),
            "billing_rule": _optional_text(item.billing_rule),
            "allocation_rule": _optional_text(item.allocation_rule),
            "completion_percent": (
                Decimal(str(item.completion_percent))
                if item.completion_percent is not None
                else None
            ),
            "erp_created_at": item.erp_created_at,
            "branch": _optional_text(item.branch),
            "approver_name": _optional_text(item.approver_name),
            "cv_enabled": item.cv_enabled,
            "time_entry_enabled": item.time_entry_enabled,
            "expenses_enabled": item.expenses_enabled,
        }

        if row is None:
            self._session.add(TaskCatalogEntry(**values))
            self._session.flush()
            return "created"

        was_active = bool(row.active)
        changed = False
        for field, value in values.items():
            if getattr(row, field) != value:
                setattr(row, field, value)
                changed = True

        if not changed:
            return "unchanged"
        self._session.flush()
        return "deactivated" if was_active and not bool(row.active) else "updated"

    def search(
        self,
        *,
        project_number: str | None = None,
        query: str | None = None,
        active_only: bool = True,
        limit: int = 200,
    ) -> tuple[TaskCatalogItem, ...]:
        statement = select(TaskCatalogEntry)
        project = _text(project_number)
        if project:
            statement = statement.where(TaskCatalogEntry.project_number == project)
        if active_only:
            statement = statement.where(TaskCatalogEntry.active.is_(True))
        wanted = _text(query)
        if wanted:
            pattern = f"%{wanted}%"
            statement = statement.where(
                or_(
                    TaskCatalogEntry.task_code.ilike(pattern),
                    TaskCatalogEntry.label.ilike(pattern),
                )
            )
        statement = statement.order_by(
            TaskCatalogEntry.project_number,
            TaskCatalogEntry.task_code,
        ).limit(max(1, min(int(limit), 500)))
        rows = self._session.scalars(statement).all()
        return tuple(self._item(row) for row in rows)
