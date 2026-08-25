from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable


MigrationAction = Callable[[Any], bool]


@dataclass(frozen=True, slots=True)
class ExcelSchemaMigration:
    """One ordered, idempotent workbook schema migration."""

    migration_id: str
    apply: MigrationAction


@dataclass(frozen=True, slots=True)
class ExcelSchemaMigrationReport:
    migration_ids: tuple[str, ...]
    changed_migration_ids: tuple[str, ...]

    @property
    def changed(self) -> bool:
        return bool(self.changed_migration_ids)


def _as_matrix(value: Any) -> list[list[Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        return [[value]]
    if not value:
        return []
    if isinstance(value[0], list):
        return value
    return [value]


def table_schema_needs_change(
    repository: Any,
    sheet_name: str,
    headers: list[str],
    table_name: str,
) -> bool:
    """Return whether the expected sheet headers/table contract is incomplete."""

    book = repository._book()
    try:
        sheet = book.sheets[sheet_name]
    except Exception:
        return True

    try:
        existing = _as_matrix(sheet.range((1, 1), (1, len(headers))).value)
        existing_headers = existing[0] if existing else []
    except Exception:
        return True
    if existing_headers != headers:
        return True

    try:
        table_names = {table.name for table in sheet.tables}
    except Exception:
        return True
    return table_name not in table_names


def ensure_table_schema(
    repository: Any,
    sheet_name: str,
    headers: list[str],
    table_name: str,
) -> bool:
    """Apply one structural table migration through the current Excel adapter."""

    return bool(repository._ensure_sheet_table(sheet_name, headers, table_name))


def run_excel_schema_migrations(
    repository: Any,
    migrations: Iterable[ExcelSchemaMigration],
) -> ExcelSchemaMigrationReport:
    """Run an explicit ordered migration set and report actual structural changes."""

    steps = tuple(migrations)
    identifiers = tuple(step.migration_id for step in steps)
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Les identifiants de migration de schéma doivent être uniques.")

    changed: list[str] = []
    for step in steps:
        if bool(step.apply(repository)):
            changed.append(step.migration_id)

    return ExcelSchemaMigrationReport(
        migration_ids=identifiers,
        changed_migration_ids=tuple(changed),
    )
