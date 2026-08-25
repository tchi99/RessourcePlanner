from __future__ import annotations

from typing import Iterable

from . import features, segment_repository
from .excel_repository import MASTER_SHEETS, ExcelRepository
from .infrastructure.excel.schema_migrations import (
    ExcelSchemaMigration,
    ExcelSchemaMigrationReport,
    ensure_table_schema,
    run_excel_schema_migrations,
)


def _save_if_changed(repo: ExcelRepository, report: ExcelSchemaMigrationReport) -> None:
    if report.changed:
        repo.save()


def ensure_availability_schema(repo: ExcelRepository) -> ExcelSchemaMigrationReport:
    """Ensure Disponibilites structurally, saving only on a real schema change."""

    MASTER_SHEETS.add(features.AVAILABILITY_SHEET)
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
    return report


def ensure_segment_schema(repo: ExcelRepository) -> ExcelSchemaMigrationReport:
    """Ensure SegmentsMO structurally, saving only on a real schema change."""

    MASTER_SHEETS.add(segment_repository.SEGMENT_SHEET)
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
    return report


def ensure_segment_fields_schema(
    repo: ExcelRepository,
    fields: Iterable[str],
) -> ExcelSchemaMigrationReport:
    """Append runtime V1 fields, then run the explicit SegmentsMO migration."""

    for field in fields:
        normalized = str(field or "").strip()
        if normalized and normalized not in segment_repository.SEGMENT_HEADERS:
            segment_repository.SEGMENT_HEADERS.append(normalized)
    return ensure_segment_schema(repo)


def install_schema_migration_compat() -> None:
    """Route high-frequency V1 schema checks through change-aware migrations."""

    if getattr(ExcelRepository, "_schema_migration_compat_installed", False):
        return

    # Existing readers resolve these module globals at execution time, so replacing
    # only the schema boundary preserves all current read/write behavior.
    features._ensure_availability_sheet = ensure_availability_schema
    segment_repository.ensure_segment_sheet = ensure_segment_schema
    segment_repository.ensure_segment_fields = ensure_segment_fields_schema

    ExcelRepository._schema_migration_compat_installed = True
