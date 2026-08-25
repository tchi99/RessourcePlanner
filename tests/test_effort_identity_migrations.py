from __future__ import annotations

from contextlib import nullcontext
from datetime import date
from pathlib import Path
import unittest
from unittest.mock import patch

from app.effort_identity_compat import ensure_effort_identity_schema
from app.effort_identity_migrations import (
    _next_effort_ids,
    _write_changed_cells,
    ensure_effort_identity_schema_controlled,
    ensure_effort_ids_controlled,
)


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


class _WriteRange:
    def __init__(self, sheet, coordinates):
        self._sheet = sheet
        self._coordinates = coordinates

    @property
    def value(self):
        return None

    @value.setter
    def value(self, value):
        self._sheet.writes.append((self._coordinates, value))


class _FakeSheet:
    def __init__(self):
        self.writes: list[object] = []

    def range(self, *coordinates):
        return _WriteRange(self, coordinates)


class _FakeRepository:
    def __init__(self):
        self.path = "fixture.xlsx"
        self._lock = nullcontext()
        self.save_calls = 0

    def save(self):
        self.save_calls += 1


class EffortIdentityMigrationTests(unittest.TestCase):
    def test_next_effort_ids_preserves_historical_format_and_sequence(self) -> None:
        year = date.today().year
        prefix = f"EFF-{year}-"

        generated = _next_effort_ids(
            [f"{prefix}00002", "EFF-2000-99999", "invalid"],
            3,
        )

        self.assertEqual(
            generated,
            [f"{prefix}00003", f"{prefix}00004", f"{prefix}00005"],
        )

    def test_changed_cells_are_grouped_into_contiguous_ranges(self) -> None:
        sheet = _FakeSheet()

        _write_changed_cells(
            sheet,
            7,
            {
                2: "EFF-A",
                3: "EFF-B",
                5: "EFF-C",
                8: "EFF-D",
                9: "EFF-E",
            },
        )

        self.assertEqual(
            sheet.writes,
            [
                (((2, 7), (3, 7)), [["EFF-A"], ["EFF-B"]]),
                (((5, 7), (5, 7)), [["EFF-C"]]),
                (((8, 7), (9, 7)), [["EFF-D"], ["EFF-E"]]),
            ],
        )

    def test_incremental_guard_does_not_save_when_ids_are_current(self) -> None:
        repo = _FakeRepository()
        expected = {2: "EFF-1"}

        with patch(
            "app.effort_identity_migrations._ensure_effort_id_column",
            return_value=False,
        ), patch(
            "app.effort_identity_migrations._seed_missing_effort_ids",
            return_value=0,
        ), patch(
            "app.effort_identity_migrations.effort_row_id_map",
            return_value=expected,
        ):
            actual = ensure_effort_ids_controlled(repo)

        self.assertEqual(actual, expected)
        self.assertEqual(repo.save_calls, 0)

    def test_incremental_guard_saves_once_when_schema_or_ids_change(self) -> None:
        repo = _FakeRepository()

        with patch(
            "app.effort_identity_migrations._ensure_effort_id_column",
            return_value=True,
        ), patch(
            "app.effort_identity_migrations._seed_missing_effort_ids",
            return_value=2,
        ), patch(
            "app.effort_identity_migrations.effort_row_id_map",
            return_value={2: "EFF-1", 3: "EFF-2"},
        ):
            ensure_effort_ids_controlled(repo)

        self.assertEqual(repo.save_calls, 1)

    def test_full_migration_reports_ids_and_backfilled_links_with_one_save(self) -> None:
        repo = _FakeRepository()

        def backfill(_repo, *, sheet_name, **_kwargs):
            return 1 if sheet_name == "DemandesMO" else 2

        with patch(
            "app.effort_identity_migrations.ensure_table_schema",
            return_value=False,
        ), patch(
            "app.effort_identity_migrations._ensure_effort_id_column",
            return_value=False,
        ), patch(
            "app.effort_identity_migrations._seed_missing_effort_ids",
            return_value=3,
        ), patch(
            "app.effort_identity_migrations.effort_row_id_map",
            return_value={4: "EFF-1", 5: "EFF-2", 6: "EFF-3"},
        ), patch(
            "app.effort_identity_migrations._backfill_source_ids",
            side_effect=backfill,
        ):
            report = ensure_effort_identity_schema_controlled(repo)

        self.assertTrue(report.changed)
        self.assertEqual(report.effort_ids_added, 3)
        self.assertEqual(report.source_links_backfilled, 3)
        self.assertEqual(repo.save_calls, 1)

    def test_full_migration_does_not_save_when_nothing_changes(self) -> None:
        repo = _FakeRepository()

        with patch(
            "app.effort_identity_migrations.ensure_table_schema",
            return_value=False,
        ), patch(
            "app.effort_identity_migrations._ensure_effort_id_column",
            return_value=False,
        ), patch(
            "app.effort_identity_migrations._seed_missing_effort_ids",
            return_value=0,
        ), patch(
            "app.effort_identity_migrations.effort_row_id_map",
            return_value={},
        ), patch(
            "app.effort_identity_migrations._backfill_source_ids",
            return_value=0,
        ):
            report = ensure_effort_identity_schema_controlled(repo)

        self.assertFalse(report.changed)
        self.assertEqual(repo.save_calls, 0)

    def test_full_schema_facade_preserves_v18_workbook_marker(self) -> None:
        repo = _FakeRepository()
        sentinel = object()

        with patch(
            "app.effort_identity_compat._declare_effort_identity_fields"
        ), patch(
            "app.effort_identity_compat.ensure_effort_identity_schema_controlled",
            return_value=sentinel,
        ) as controlled:
            first = ensure_effort_identity_schema(repo)
            second = ensure_effort_identity_schema(repo)

        self.assertIs(first, sentinel)
        self.assertEqual(controlled.call_count, 1)
        self.assertFalse(second.changed)

    def test_effort_identity_compat_no_longer_delegates_migration_to_v18_privates(self) -> None:
        source = (APP / "effort_identity_compat.py").read_text(encoding="utf-8")

        self.assertNotIn("return v18._ensure_effort_ids(repo)", source)
        self.assertNotIn("v18.ensure_v18_schema(repo)", source)
        self.assertIn("v18._ensure_effort_ids = ensure_effort_ids_controlled", source)
        self.assertIn("v18.ensure_v18_schema = ensure_effort_identity_schema", source)
        self.assertIn("v18._install_stable_link_wrappers()", source)

    def test_read_guard_is_preserved_but_routes_through_controlled_boundary(self) -> None:
        guard_source = (APP / "effort_identity_guard.py").read_text(encoding="utf-8")
        migration_source = (APP / "effort_identity_migrations.py").read_text(encoding="utf-8")

        self.assertIn("ensure_effort_ids(self)", guard_source)
        self.assertNotIn("repo.efforts(", migration_source)
        self.assertIn("_write_changed_cells", migration_source)
        self.assertIn("if report.changed:", migration_source)


if __name__ == "__main__":
    unittest.main()
