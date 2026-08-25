from __future__ import annotations

from typing import Iterable

from . import features, segment_repository, v13, v14, v14_engine, v15_engine
from .excel_repository import (
    DEMAND_HEADERS,
    HISTORY_HEADERS,
    MASTER_SHEETS,
    ExcelRepository,
    _as_matrix,
)
from .infrastructure.excel.schema_migrations import (
    ExcelSchemaMigration,
    ExcelSchemaMigrationReport,
    ensure_table_schema,
    run_excel_schema_migrations,
)


_BASE_MIGRATION_IDS = ("demands.table.v1", "history.table.v1")
_AVAILABILITY_MIGRATION_IDS = ("availability.table.v1",)
_SEGMENT_MIGRATION_IDS = ("segments.table.v1",)
_V14_MIGRATION_IDS = ("segments.table.v14", "allocations.table.v14")
_V15_MIGRATION_IDS = ("allocations.table.v15",)

_LEGACY_ENSURE_SHEET_TABLE = ExcelRepository._ensure_sheet_table


def _unchanged_report(*migration_ids: str) -> ExcelSchemaMigrationReport:
    return ExcelSchemaMigrationReport(
        migration_ids=tuple(migration_ids),
        changed_migration_ids=(),
    )


def _save_if_changed(repo: ExcelRepository, report: ExcelSchemaMigrationReport) -> None:
    if report.changed:
        repo.save()


def _table_schema_needs_change(
    repo: ExcelRepository,
    sheet_name: str,
    headers: list[str],
    table_name: str,
) -> bool:
    """Inspect only the structural contract needed by the V1 migration runner."""

    book = repo._book()
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


def _ensure_sheet_table_change_aware(
    repo: ExcelRepository,
    sheet_name: str,
    headers: list[str],
    table_name: str,
) -> bool:
    """Run the historical formatter only when the structural schema is incomplete."""

    if not _table_schema_needs_change(repo, sheet_name, headers, table_name):
        return False

    _LEGACY_ENSURE_SHEET_TABLE(repo, sheet_name, headers, table_name)
    return True


def ensure_base_app_schema(repo: ExcelRepository) -> ExcelSchemaMigrationReport:
    """Ensure DemandesMO and Historique, saving only after an actual schema change."""

    report = run_excel_schema_migrations(
        repo,
        (
            ExcelSchemaMigration(
                "demands.table.v1",
                lambda current: ensure_table_schema(
                    current,
                    "DemandesMO",
                    DEMAND_HEADERS,
                    "DemandesMOTable",
                ),
            ),
            ExcelSchemaMigration(
                "history.table.v1",
                lambda current: ensure_table_schema(
                    current,
                    "Historique",
                    HISTORY_HEADERS,
                    "HistoriqueTable",
                ),
            ),
        ),
    )
    _save_if_changed(repo, report)
    return report


def ensure_availability_schema(repo: ExcelRepository) -> ExcelSchemaMigrationReport:
    """Ensure Disponibilites structurally, saving only on a real schema change."""

    MASTER_SHEETS.add(features.AVAILABILITY_SHEET)
    marker = (str(repo.path or ""), tuple(features.AVAILABILITY_HEADERS))
    if getattr(repo, "_v1_availability_schema_marker", None) == marker:
        return _unchanged_report(*_AVAILABILITY_MIGRATION_IDS)

    report = run_excel_schema_migrations(
        repo,
        (
            ExcelSchemaMigration(
                "availability.table.v1",
                lambda current: ensure_table_schema(
                    current,
                    features.AVAILABILITY_SHEET,
                    features.AVAILABILITY_HEADERS,
                    features.AVAILABILITY_TABLE,
                ),
            ),
        ),
    )
    _save_if_changed(repo, report)
    if not _table_schema_needs_change(
        repo,
        features.AVAILABILITY_SHEET,
        features.AVAILABILITY_HEADERS,
        features.AVAILABILITY_TABLE,
    ):
        repo._v1_availability_schema_marker = marker
    return report


def ensure_segment_schema(repo: ExcelRepository) -> ExcelSchemaMigrationReport:
    """Ensure SegmentsMO structurally, saving only on a real schema change."""

    MASTER_SHEETS.add(segment_repository.SEGMENT_SHEET)
    marker = (str(repo.path or ""), tuple(segment_repository.SEGMENT_HEADERS))
    if getattr(repo, "_v1_segment_schema_marker", None) == marker:
        return _unchanged_report(*_SEGMENT_MIGRATION_IDS)

    report = run_excel_schema_migrations(
        repo,
        (
            ExcelSchemaMigration(
                "segments.table.v1",
                lambda current: ensure_table_schema(
                    current,
                    segment_repository.SEGMENT_SHEET,
                    segment_repository.SEGMENT_HEADERS,
                    segment_repository.SEGMENT_TABLE,
                ),
            ),
        ),
    )
    _save_if_changed(repo, report)
    if not _table_schema_needs_change(
        repo,
        segment_repository.SEGMENT_SHEET,
        segment_repository.SEGMENT_HEADERS,
        segment_repository.SEGMENT_TABLE,
    ):
        repo._v1_segment_schema_marker = marker
    return report


def ensure_segment_fields_schema(
    repo: ExcelRepository,
    fields: Iterable[str],
) -> ExcelSchemaMigrationReport:
    """Append optional V1 fields, then run the explicit SegmentsMO migration."""

    for field in fields:
        normalized = str(field or "").strip()
        if normalized and normalized not in segment_repository.SEGMENT_HEADERS:
            segment_repository.SEGMENT_HEADERS.append(normalized)
    return ensure_segment_schema(repo)


def ensure_v14_schema(repo: ExcelRepository) -> ExcelSchemaMigrationReport:
    """Ensure the V1.4 SegmentsMO/AllocationsMO extensions as one migration set."""

    for header in v14_engine.SEGMENT_EXTRA_HEADERS:
        if header not in segment_repository.SEGMENT_HEADERS:
            segment_repository.SEGMENT_HEADERS.append(header)
    MASTER_SHEETS.add(segment_repository.SEGMENT_SHEET)
    MASTER_SHEETS.add(v14_engine.ALLOCATION_SHEET)

    marker = (
        str(repo.path or ""),
        tuple(segment_repository.SEGMENT_HEADERS),
        tuple(v14_engine.ALLOCATION_HEADERS),
    )
    if getattr(repo, "_v1_v14_schema_marker", None) == marker:
        return _unchanged_report(*_V14_MIGRATION_IDS)

    report = run_excel_schema_migrations(
        repo,
        (
            ExcelSchemaMigration(
                "segments.table.v14",
                lambda current: ensure_table_schema(
                    current,
                    segment_repository.SEGMENT_SHEET,
                    segment_repository.SEGMENT_HEADERS,
                    segment_repository.SEGMENT_TABLE,
                ),
            ),
            ExcelSchemaMigration(
                "allocations.table.v14",
                lambda current: ensure_table_schema(
                    current,
                    v14_engine.ALLOCATION_SHEET,
                    v14_engine.ALLOCATION_HEADERS,
                    v14_engine.ALLOCATION_TABLE,
                ),
            ),
        ),
    )
    _save_if_changed(repo, report)
    if not _table_schema_needs_change(
        repo,
        segment_repository.SEGMENT_SHEET,
        segment_repository.SEGMENT_HEADERS,
        segment_repository.SEGMENT_TABLE,
    ) and not _table_schema_needs_change(
        repo,
        v14_engine.ALLOCATION_SHEET,
        v14_engine.ALLOCATION_HEADERS,
        v14_engine.ALLOCATION_TABLE,
    ):
        repo._v1_v14_schema_marker = marker
    return report


def ensure_v15_schema(repo: ExcelRepository) -> ExcelSchemaMigrationReport:
    """Ensure the manual-allocation columns introduced by V1.5."""

    for header in v15_engine.ALLOCATION_EXTRA_HEADERS:
        if header not in v14_engine.ALLOCATION_HEADERS:
            v14_engine.ALLOCATION_HEADERS.append(header)
    MASTER_SHEETS.add(v14_engine.ALLOCATION_SHEET)

    marker = (str(repo.path or ""), tuple(v14_engine.ALLOCATION_HEADERS))
    if getattr(repo, "_v1_v15_schema_marker", None) == marker:
        return _unchanged_report(*_V15_MIGRATION_IDS)

    report = run_excel_schema_migrations(
        repo,
        (
            ExcelSchemaMigration(
                "allocations.table.v15",
                lambda current: ensure_table_schema(
                    current,
                    v14_engine.ALLOCATION_SHEET,
                    v14_engine.ALLOCATION_HEADERS,
                    v14_engine.ALLOCATION_TABLE,
                ),
            ),
        ),
    )
    _save_if_changed(repo, report)
    if not _table_schema_needs_change(
        repo,
        v14_engine.ALLOCATION_SHEET,
        v14_engine.ALLOCATION_HEADERS,
        v14_engine.ALLOCATION_TABLE,
    ):
        repo._v1_v15_schema_marker = marker
        repo._v15_ready_path = str(repo.path or "")
    return report


def install_schema_migration_compat() -> None:
    """Route V1 schema checks through explicit, change-aware migrations."""

    if getattr(ExcelRepository, "_schema_migration_compat_installed", False):
        return

    # Predeclare known V1.4/V1.5 columns before the workbook is connected so earlier
    # V1 wrappers do not successively rewrite the same table during one startup.
    for header in v14_engine.SEGMENT_EXTRA_HEADERS:
        if header not in segment_repository.SEGMENT_HEADERS:
            segment_repository.SEGMENT_HEADERS.append(header)
    for header in v15_engine.ALLOCATION_EXTRA_HEADERS:
        if header not in v14_engine.ALLOCATION_HEADERS:
            v14_engine.ALLOCATION_HEADERS.append(header)

    ExcelRepository._ensure_sheet_table = _ensure_sheet_table_change_aware
    ExcelRepository.ensure_app_sheets = ensure_base_app_schema

    # Existing readers/installers resolve these names at execution time or through
    # aliases already imported by V1 modules. Patch both forms explicitly.
    features._ensure_availability_sheet = ensure_availability_schema
    segment_repository.ensure_segment_sheet = ensure_segment_schema
    segment_repository.ensure_segment_fields = ensure_segment_fields_schema
    v13._ensure_v13_sheets = ensure_segment_schema
    v14_engine.ensure_v14_sheets = ensure_v14_schema
    v14.ensure_v14_sheets = ensure_v14_schema
    v15_engine.ensure_v15_sheets = ensure_v15_schema

    ExcelRepository._schema_migration_compat_installed = True
