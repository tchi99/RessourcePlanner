from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from . import v13, v18
from .excel_repository import DEMAND_HEADERS, ExcelRepository, _as_matrix, _best_header_row
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
class EffortIdentityMigrationReport:
    schema: ExcelSchemaMigrationReport
    data: ExcelDataMigrationReport

    @property
    def changed(self) -> bool:
        return self.schema.changed or self.data.changed

    @property
    def effort_ids_added(self) -> int:
        return next(
            (
                count
                for migration_id, count in self.data.change_counts
                if migration_id == "efforts.seed_missing_ids.v1"
            ),
            0,
        )

    @property
    def source_links_backfilled(self) -> int:
        return sum(
            count
            for migration_id, count in self.data.change_counts
            if migration_id.startswith("effort_links.backfill_")
        )


def _effort_table_and_header(repo: ExcelRepository) -> tuple[Any | None, int, int, list[Any]]:
    """Locate the Liste_Effort header using the historical V1.8 rules."""

    sheet = repo._book().sheets[v18.EFFORT_SHEET]

    try:
        for table in sheet.tables:
            first_row = int(table.range.row)
            first_col = int(table.range.column)
            last_col = int(table.range.last_cell.column)
            headers = _as_matrix(
                sheet.range((first_row, first_col), (first_row, last_col)).value
            )
            row = headers[0] if headers else []
            if any(str(value or "").strip() == "N° projet" for value in row):
                return table, first_row, first_col, row
    except Exception:
        pass

    used = sheet.used_range
    matrix = _as_matrix(used.value)
    header_relative = _best_header_row(matrix)
    header_row = int(used.row) + header_relative - 1
    first_col = int(used.column)
    last_col = int(used.last_cell.column)
    headers = _as_matrix(
        sheet.range((header_row, first_col), (header_row, last_col)).value
    )
    return None, header_row, first_col, headers[0] if headers else []


def _ensure_effort_id_column(repo: ExcelRepository) -> bool:
    sheet = repo._book().sheets[v18.EFFORT_SHEET]
    table, header_row, first_col, headers = _effort_table_and_header(repo)

    for raw in headers:
        if str(raw or "").strip() == v18.EFFORT_ID_FIELD:
            return False

    last_header_offset = max(
        (index for index, value in enumerate(headers) if value not in (None, "")),
        default=-1,
    )
    target_col = first_col + last_header_offset + 1
    sheet.range((header_row, target_col)).value = v18.EFFORT_ID_FIELD

    if table is not None:
        try:
            last_row = max(int(table.range.last_cell.row), header_row + 1)
            table.resize(
                sheet.range(
                    (int(table.range.row), int(table.range.column)),
                    (last_row, target_col),
                )
            )
        except Exception:
            pass

    try:
        source = sheet.range((header_row, max(target_col - 1, first_col)))
        target = sheet.range((header_row, target_col))
        target.color = source.color
        target.font.bold = source.font.bold
        target.font.color = source.font.color
    except Exception:
        pass
    return True


def _effort_id_column(repo: ExcelRepository) -> tuple[int, int]:
    _table, header_row, first_col, headers = _effort_table_and_header(repo)
    for offset, raw in enumerate(headers):
        if str(raw or "").strip() == v18.EFFORT_ID_FIELD:
            return header_row, first_col + offset
    raise RuntimeError("La colonne IDEffort n'est pas disponible après la migration de schéma.")


def _next_effort_ids(existing: list[str], count: int) -> list[str]:
    year = date.today().year
    prefix = f"EFF-{year}-"
    maximum = 0
    for value in existing:
        text = str(value or "").strip()
        if not text.startswith(prefix):
            continue
        try:
            maximum = max(maximum, int(text[len(prefix) :]))
        except ValueError:
            pass
    return [f"{prefix}{maximum + index:05d}" for index in range(1, count + 1)]


def _write_changed_cells(
    sheet: Any,
    column: int,
    changed_by_row: dict[int, Any],
) -> None:
    """Write only changed cells, grouped into contiguous row ranges."""

    if not changed_by_row:
        return
    rows = sorted(changed_by_row)
    block = [rows[0]]

    def flush(block_rows: list[int]) -> None:
        first = block_rows[0]
        last = block_rows[-1]
        values = [[changed_by_row[row]] for row in block_rows]
        sheet.range((first, column), (last, column)).value = values

    for row in rows[1:]:
        if row == block[-1] + 1:
            block.append(row)
            continue
        flush(block)
        block = [row]
    flush(block)


def _seed_missing_effort_ids(repo: ExcelRepository) -> int:
    _header_row, id_col = _effort_id_column(repo)
    rows = [
        row
        for row in repo._sheet_as_records(v18.EFFORT_SHEET, "N° projet")
        if row.get("N° projet") not in (None, "")
    ]
    existing = [
        str(row.get(v18.EFFORT_ID_FIELD) or "").strip()
        for row in rows
        if str(row.get(v18.EFFORT_ID_FIELD) or "").strip()
    ]
    missing = [
        row for row in rows if not str(row.get(v18.EFFORT_ID_FIELD) or "").strip()
    ]
    identifiers = _next_effort_ids(existing, len(missing))
    changed = {
        int(row["_row"]): identifier
        for row, identifier in zip(missing, identifiers)
    }
    if changed:
        _write_changed_cells(repo._book().sheets[v18.EFFORT_SHEET], id_col, changed)
    return len(changed)


def effort_row_id_map(repo: ExcelRepository) -> dict[int, str]:
    """Return the current stable effort identity map without invoking repo.efforts()."""

    return {
        int(row["_row"]): str(row.get(v18.EFFORT_ID_FIELD) or "").strip()
        for row in repo._sheet_as_records(v18.EFFORT_SHEET, "N° projet")
        if row.get("_row") and str(row.get(v18.EFFORT_ID_FIELD) or "").strip()
    }


def _backfill_source_ids(
    repo: ExcelRepository,
    *,
    sheet_name: str,
    headers: list[str],
    key_field: str,
    row_to_id: dict[int, str],
) -> int:
    if v18.SOURCE_EFFORT_ID_FIELD not in headers:
        return 0

    records = repo._sheet_as_records(sheet_name, key_field)
    if not records:
        return 0
    target_col = headers.index(v18.SOURCE_EFFORT_ID_FIELD) + 1
    changed: dict[int, str] = {}

    for row in records:
        if str(row.get(v18.SOURCE_EFFORT_ID_FIELD) or "").strip():
            continue
        try:
            source_row = int(float(row.get(v13.SOURCE_EFFORT_FIELD)))
        except (TypeError, ValueError):
            continue
        identifier = row_to_id.get(source_row)
        if identifier:
            changed[int(row["_row"])] = identifier

    if changed:
        _write_changed_cells(repo._book().sheets[sheet_name], target_col, changed)
    return len(changed)


def ensure_effort_ids_controlled(repo: ExcelRepository) -> dict[int, str]:
    """Incrementally assign IDs to direct Excel rows and save only when required."""

    with repo._lock:
        schema_report = run_excel_schema_migrations(
            repo,
            (
                ExcelSchemaMigration("efforts.ideffort_column.v1", _ensure_effort_id_column),
            ),
        )
        data_report = run_excel_data_migrations(
            repo,
            (
                ExcelDataMigration("efforts.seed_missing_ids.v1", _seed_missing_effort_ids),
            ),
        )
        if schema_report.changed or data_report.changed:
            repo.save()
        return effort_row_id_map(repo)


def ensure_effort_identity_schema_controlled(
    repo: ExcelRepository,
) -> EffortIdentityMigrationReport:
    """Migrate effort IDs and stable source links with one final save."""

    with repo._lock:
        schema_report = run_excel_schema_migrations(
            repo,
            (
                ExcelSchemaMigration(
                    "demands.source_effort_id.v18",
                    lambda current: ensure_table_schema(
                        current,
                        "DemandesMO",
                        DEMAND_HEADERS,
                        "DemandesMOTable",
                    ),
                ),
                ExcelSchemaMigration(
                    "segments.source_effort_id.v18",
                    lambda current: ensure_table_schema(
                        current,
                        v13.SEGMENT_SHEET,
                        v13.SEGMENT_HEADERS,
                        v13.SEGMENT_TABLE,
                    ),
                ),
                ExcelSchemaMigration("efforts.ideffort_column.v1", _ensure_effort_id_column),
            ),
        )

        id_seed_report = run_excel_data_migrations(
            repo,
            (
                ExcelDataMigration("efforts.seed_missing_ids.v1", _seed_missing_effort_ids),
            ),
        )
        row_to_id = effort_row_id_map(repo)
        link_report = run_excel_data_migrations(
            repo,
            (
                ExcelDataMigration(
                    "effort_links.backfill_demands.v18",
                    lambda current: _backfill_source_ids(
                        current,
                        sheet_name="DemandesMO",
                        headers=DEMAND_HEADERS,
                        key_field="NoDemande",
                        row_to_id=row_to_id,
                    ),
                ),
                ExcelDataMigration(
                    "effort_links.backfill_segments.v18",
                    lambda current: _backfill_source_ids(
                        current,
                        sheet_name=v13.SEGMENT_SHEET,
                        headers=v13.SEGMENT_HEADERS,
                        key_field="IDSegment",
                        row_to_id=row_to_id,
                    ),
                ),
            ),
        )
        data_report = ExcelDataMigrationReport(
            migration_ids=(*id_seed_report.migration_ids, *link_report.migration_ids),
            change_counts=(*id_seed_report.change_counts, *link_report.change_counts),
        )
        report = EffortIdentityMigrationReport(schema=schema_report, data=data_report)
        if report.changed:
            repo.save()
        return report
