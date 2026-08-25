from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from app.infrastructure.excel.schema_migrations import (
    ExcelSchemaMigration,
    run_excel_schema_migrations,
)
from app import schema_migration_compat as schema
from app.runtime_composition import composition_manifest
from app.segment_repository import SEGMENT_HEADERS


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


class _FakeRange:
    def __init__(self, value):
        self.value = value


class _FakeTable:
    def __init__(self, name: str):
        self.name = name


class _FakeSheet:
    def __init__(self, headers: list[str], table_name: str | None = None):
        self.headers = list(headers)
        self.tables = [_FakeTable(table_name)] if table_name else []

    def range(self, *_args):
        return _FakeRange([list(self.headers)])


class _FakeBook:
    def __init__(self, sheets):
        self.sheets = sheets


class _FakeRepository:
    def __init__(self, *, table_change: bool = False):
        self.path = "fixture.xlsx"
        self.table_change = table_change
        self.ensure_calls: list[tuple[str, tuple[str, ...], str]] = []
        self.save_calls = 0

    def _ensure_sheet_table(self, sheet, headers, table):
        self.ensure_calls.append((sheet, tuple(headers), table))
        changed = self.table_change
        self.table_change = False
        return changed

    def save(self):
        self.save_calls += 1


class SchemaMigrationTests(unittest.TestCase):
    def test_runner_reports_only_changed_steps(self) -> None:
        events: list[str] = []
        report = run_excel_schema_migrations(
            object(),
            (
                ExcelSchemaMigration("one", lambda _repo: events.append("one") or False),
                ExcelSchemaMigration("two", lambda _repo: events.append("two") or True),
            ),
        )

        self.assertEqual(events, ["one", "two"])
        self.assertEqual(report.migration_ids, ("one", "two"))
        self.assertEqual(report.changed_migration_ids, ("two",))
        self.assertTrue(report.changed)

    def test_runner_rejects_duplicate_migration_ids(self) -> None:
        with self.assertRaises(ValueError):
            run_excel_schema_migrations(
                object(),
                (
                    ExcelSchemaMigration("same", lambda _repo: False),
                    ExcelSchemaMigration("same", lambda _repo: False),
                ),
            )

    def test_change_aware_table_guard_skips_legacy_formatter_when_schema_matches(self) -> None:
        headers = ["A", "B"]
        repo = type(
            "Repo",
            (),
            {"_book": lambda self: _FakeBook({"Sheet": _FakeSheet(headers, "Table")})},
        )()

        with patch.object(schema, "_LEGACY_ENSURE_SHEET_TABLE") as legacy:
            changed = schema._ensure_sheet_table_change_aware(
                repo,
                "Sheet",
                headers,
                "Table",
            )

        self.assertFalse(changed)
        legacy.assert_not_called()

    def test_change_aware_table_guard_runs_legacy_formatter_on_header_change(self) -> None:
        repo = type(
            "Repo",
            (),
            {"_book": lambda self: _FakeBook({"Sheet": _FakeSheet(["Old"], "Table")})},
        )()

        with patch.object(schema, "_LEGACY_ENSURE_SHEET_TABLE") as legacy:
            changed = schema._ensure_sheet_table_change_aware(
                repo,
                "Sheet",
                ["New"],
                "Table",
            )

        self.assertTrue(changed)
        legacy.assert_called_once()

    def test_availability_schema_saves_once_then_uses_marker(self) -> None:
        repo = _FakeRepository(table_change=True)
        with patch.object(schema, "_table_schema_needs_change", return_value=False):
            first = schema.ensure_availability_schema(repo)
            second = schema.ensure_availability_schema(repo)

        self.assertTrue(first.changed)
        self.assertFalse(second.changed)
        self.assertEqual(repo.save_calls, 1)
        self.assertEqual(len(repo.ensure_calls), 1)

    def test_segment_fields_migration_appends_field_once_and_avoids_second_save(self) -> None:
        repo = _FakeRepository(table_change=True)
        field = "TestControlledMigrationField"
        try:
            with patch.object(schema, "_table_schema_needs_change", return_value=False):
                first = schema.ensure_segment_fields_schema(repo, [field])
                second = schema.ensure_segment_fields_schema(repo, [field])

            self.assertTrue(first.changed)
            self.assertFalse(second.changed)
            self.assertEqual(SEGMENT_HEADERS.count(field), 1)
            self.assertEqual(repo.save_calls, 1)
        finally:
            if field in SEGMENT_HEADERS:
                SEGMENT_HEADERS.remove(field)

    def test_schema_migrations_install_before_legacy_feature_wrappers(self) -> None:
        names = [step.name for step in composition_manifest()]

        self.assertLess(names.index("runtime_optimizations"), names.index("schema_migrations"))
        self.assertLess(names.index("schema_migrations"), names.index("features"))
        self.assertLess(names.index("schema_migrations"), names.index("v13_features"))
        self.assertLess(names.index("schema_migrations"), names.index("v14_features"))
        self.assertLess(names.index("schema_migrations"), names.index("runtime_performance"))

    def test_compat_layer_routes_v14_and_v15_schema_ensures_through_registry(self) -> None:
        source = (APP / "schema_migration_compat.py").read_text(encoding="utf-8")

        self.assertIn("v14_engine.ensure_v14_sheets = ensure_v14_schema", source)
        self.assertIn("v14.ensure_v14_sheets = ensure_v14_schema", source)
        self.assertIn("v15_engine.ensure_v15_sheets = ensure_v15_schema", source)
        self.assertIn("ExcelRepository.ensure_app_sheets = ensure_base_app_schema", source)
        self.assertIn("ExcelRepository._ensure_sheet_table = _ensure_sheet_table_change_aware", source)


if __name__ == "__main__":
    unittest.main()
