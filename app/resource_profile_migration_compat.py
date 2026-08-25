from __future__ import annotations

from dataclasses import dataclass

from . import v16_refinements
from .excel_repository import MASTER_SHEETS, ExcelRepository
from .infrastructure.excel.data_migrations import (
    ExcelDataMigration,
    ExcelDataMigrationReport,
    run_excel_data_migrations,
)
from .infrastructure.excel.schema_migrations import (
    ExcelSchemaMigration,
    ExcelSchemaMigrationReport,
    ensure_table_schema,
    run_excel_schema_migrations,
)


@dataclass(frozen=True, slots=True)
class ResourceProfileMigrationReport:
    schema: ExcelSchemaMigrationReport
    data: ExcelDataMigrationReport

    @property
    def changed(self) -> bool:
        return self.schema.changed or self.data.changed

    @property
    def profiles_added(self) -> int:
        return self.data.total_changes


def _append_missing_resource_profiles(repo: ExcelRepository) -> int:
    existing = {
        str(row.get("Technicien") or "").strip()
        for row in v16_refinements._profile_records(repo)
        if str(row.get("Technicien") or "").strip()
    }

    missing: list[str] = []
    for technician in repo.technicians():
        name = str(technician.get("name") or "").strip()
        if not name or name in existing:
            continue
        missing.append(name)
        existing.add(name)

    if not missing:
        return 0

    headers = v16_refinements.RESOURCE_PROFILE_HEADERS
    sheet = repo._book().sheets[v16_refinements.RESOURCE_PROFILE_SHEET]
    last = sheet.cells.last_cell.row
    last_used = sheet.range(f"A{last}").end("up").row
    first_row = max(2, int(last_used) + 1)
    last_row = first_row + len(missing) - 1

    matrix = [
        [name if header == "Technicien" else None for header in headers]
        for name in missing
    ]
    sheet.range((first_row, 1), (last_row, len(headers))).value = matrix

    try:
        table = sheet.tables[v16_refinements.RESOURCE_PROFILE_TABLE]
        table.resize(sheet.range((1, 1), (last_row, len(headers))))
    except Exception:
        pass

    return len(missing)


def ensure_resource_profiles_controlled(
    repo: ExcelRepository,
) -> ResourceProfileMigrationReport:
    """Ensure RessourcesMO and synchronize missing technicians with one final save."""

    MASTER_SHEETS.add(v16_refinements.RESOURCE_PROFILE_SHEET)
    with repo._lock:
        schema_report = run_excel_schema_migrations(
            repo,
            (
                ExcelSchemaMigration(
                    "resource_profiles.table.v16",
                    lambda current: ensure_table_schema(
                        current,
                        v16_refinements.RESOURCE_PROFILE_SHEET,
                        v16_refinements.RESOURCE_PROFILE_HEADERS,
                        v16_refinements.RESOURCE_PROFILE_TABLE,
                    ),
                ),
            ),
        )
        data_report = run_excel_data_migrations(
            repo,
            (
                ExcelDataMigration(
                    "resource_profiles.seed_missing_technicians.v1",
                    _append_missing_resource_profiles,
                ),
            ),
        )
        report = ResourceProfileMigrationReport(
            schema=schema_report,
            data=data_report,
        )
        if report.changed:
            repo.save()
        return report


def install_resource_profile_migration_compat() -> None:
    """Route RessourcesMO setup through explicit schema/data migrations."""

    if getattr(ExcelRepository, "_resource_profile_migration_compat_installed", False):
        return

    v16_refinements.ensure_resource_profiles = ensure_resource_profiles_controlled
    ExcelRepository._resource_profile_migration_compat_installed = True
