from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.infrastructure.excel.data_migrations import (
    ExcelDataMigration,
    run_excel_data_migrations,
)
from app.resource_profile_migration_compat import (
    _append_missing_resource_profiles,
    ensure_resource_profiles_controlled,
)
from app.runtime_composition import composition_manifest
from app import v16_refinements


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


class _EndCell:
    def __init__(self, row: int):
        self.row = row


class _AnchorRange:
    def __init__(self, last_used_row: int):
        self._last_used_row = last_used_row

    def end(self, _direction: str):
        return _EndCell(self._last_used_row)


class _WriteRange:
    def __init__(self, sheet, coordinates):
        self._sheet = sheet
        self._coordinates = coordinates
        self._value = None

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        self._value = value
        self._sheet.writes.append((self._coordinates, value))


class _FakeTable:
    def __init__(self):
        self.resize_calls = []

    def resize(self, target):
        self.resize_calls.append(target)


class _FakeSheet:
    def __init__(self, last_used_row: int = 2):
        self.cells = SimpleNamespace(last_cell=SimpleNamespace(row=1000))
        self.last_used_row = last_used_row
        self.writes = []
        self.table = _FakeTable()
        self.tables = {v16_refinements.RESOURCE_PROFILE_TABLE: self.table}

    def range(self, *coordinates):
        if len(coordinates) == 1 and isinstance(coordinates[0], str):
            return _AnchorRange(self.last_used_row)
        return _WriteRange(self, coordinates)


class _FakeRepository:
    def __init__(self, technicians, *, schema_changed=False, sheet=None):
        self.path = "fixture.xlsx"
        self._lock = nullcontext()
        self._technicians = list(technicians)
        self.schema_changed = schema_changed
        self.save_calls = 0
        self.ensure_calls = 0
        self.sheet = sheet or _FakeSheet()
        self.book = SimpleNamespace(
            sheets={v16_refinements.RESOURCE_PROFILE_SHEET: self.sheet}
        )

    def technicians(self):
        return list(self._technicians)

    def _book(self):
        return self.book

    def _ensure_sheet_table(self, _sheet, _headers, _table):
        self.ensure_calls += 1
        changed = self.schema_changed
        self.schema_changed = False
        return changed

    def save(self):
        self.save_calls += 1


class ResourceProfileMigrationTests(unittest.TestCase):
    def test_data_runner_reports_change_counts(self) -> None:
        report = run_excel_data_migrations(
            object(),
            (
                ExcelDataMigration("one", lambda _repo: 0),
                ExcelDataMigration("two", lambda _repo: 3),
            ),
        )

        self.assertEqual(report.migration_ids, ("one", "two"))
        self.assertEqual(report.change_counts, (("one", 0), ("two", 3)))
        self.assertEqual(report.changed_migration_ids, ("two",))
        self.assertEqual(report.total_changes, 3)
        self.assertTrue(report.changed)

    def test_data_runner_rejects_duplicate_ids_and_negative_counts(self) -> None:
        with self.assertRaises(ValueError):
            run_excel_data_migrations(
                object(),
                (
                    ExcelDataMigration("same", lambda _repo: 0),
                    ExcelDataMigration("same", lambda _repo: 1),
                ),
            )
        with self.assertRaises(ValueError):
            run_excel_data_migrations(
                object(),
                (ExcelDataMigration("negative", lambda _repo: -1),),
            )

    def test_missing_profiles_are_written_as_one_contiguous_matrix(self) -> None:
        repo = _FakeRepository(
            [
                {"name": "Alex"},
                {"name": "Benoit"},
                {"name": "Chloe"},
            ],
            sheet=_FakeSheet(last_used_row=2),
        )
        existing = [{"Technicien": "Alex", "_row": 2}]

        with patch.object(v16_refinements, "_profile_records", return_value=existing):
            added = _append_missing_resource_profiles(repo)

        self.assertEqual(added, 2)
        self.assertEqual(len(repo.sheet.writes), 1)
        coordinates, matrix = repo.sheet.writes[0]
        self.assertEqual(coordinates[0], (3, 1))
        self.assertEqual(coordinates[1][0], 4)
        self.assertEqual(matrix[0][0], "Benoit")
        self.assertEqual(matrix[1][0], "Chloe")
        self.assertEqual(len(matrix[0]), len(v16_refinements.RESOURCE_PROFILE_HEADERS))
        self.assertEqual(repo.save_calls, 0)

    def test_controlled_profile_setup_saves_once_for_schema_and_data_changes(self) -> None:
        repo = _FakeRepository([{"name": "Alex"}], schema_changed=True)

        with patch.object(v16_refinements, "_profile_records", return_value=[]), patch(
            "app.resource_profile_migration_compat._append_missing_resource_profiles",
            return_value=1,
        ):
            report = ensure_resource_profiles_controlled(repo)

        self.assertTrue(report.changed)
        self.assertTrue(report.schema.changed)
        self.assertEqual(report.profiles_added, 1)
        self.assertEqual(repo.save_calls, 1)

    def test_controlled_profile_setup_does_not_save_when_already_current(self) -> None:
        repo = _FakeRepository([{"name": "Alex"}], schema_changed=False)

        with patch(
            "app.resource_profile_migration_compat._append_missing_resource_profiles",
            return_value=0,
        ):
            report = ensure_resource_profiles_controlled(repo)

        self.assertFalse(report.changed)
        self.assertEqual(report.profiles_added, 0)
        self.assertEqual(repo.save_calls, 0)

    def test_resource_profile_migration_is_installed_before_runtime_performance_cache(self) -> None:
        names = [step.name for step in composition_manifest()]

        self.assertLess(names.index("v16_refinements"), names.index("resource_profile_migrations"))
        self.assertLess(names.index("resource_profile_migrations"), names.index("resource_management"))
        self.assertLess(names.index("resource_profile_migrations"), names.index("runtime_performance"))

    def test_compat_avoids_per_technician_append_save_loop(self) -> None:
        source = (APP / "resource_profile_migration_compat.py").read_text(encoding="utf-8")

        self.assertNotIn("_append_dict_row", source)
        self.assertIn("sheet.range((first_row, 1), (last_row, len(headers))).value = matrix", source)
        self.assertIn("if report.changed:", source)
        self.assertIn("repo.save()", source)


if __name__ == "__main__":
    unittest.main()
