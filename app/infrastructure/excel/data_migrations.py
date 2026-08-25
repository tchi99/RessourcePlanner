from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable


DataMigrationAction = Callable[[Any], int]


@dataclass(frozen=True, slots=True)
class ExcelDataMigration:
    """One ordered, idempotent workbook data migration."""

    migration_id: str
    apply: DataMigrationAction


@dataclass(frozen=True, slots=True)
class ExcelDataMigrationReport:
    migration_ids: tuple[str, ...]
    change_counts: tuple[tuple[str, int], ...]

    @property
    def changed_migration_ids(self) -> tuple[str, ...]:
        return tuple(
            migration_id
            for migration_id, count in self.change_counts
            if count > 0
        )

    @property
    def changed(self) -> bool:
        return bool(self.changed_migration_ids)

    @property
    def total_changes(self) -> int:
        return sum(count for _migration_id, count in self.change_counts)


def run_excel_data_migrations(
    repository: Any,
    migrations: Iterable[ExcelDataMigration],
) -> ExcelDataMigrationReport:
    """Run ordered data migrations and report the number of records changed."""

    steps = tuple(migrations)
    identifiers = tuple(step.migration_id for step in steps)
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Les identifiants de migration de données doivent être uniques.")

    counts: list[tuple[str, int]] = []
    for step in steps:
        count = int(step.apply(repository))
        if count < 0:
            raise ValueError("Une migration de données ne peut pas rapporter un nombre négatif.")
        counts.append((step.migration_id, count))

    return ExcelDataMigrationReport(
        migration_ids=identifiers,
        change_counts=tuple(counts),
    )
