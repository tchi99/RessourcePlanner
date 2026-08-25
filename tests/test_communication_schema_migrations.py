from __future__ import annotations

from contextlib import nullcontext
from datetime import date
from pathlib import Path
import unittest

from app.communication_excel import (
    BATCH_SHEET,
    CONTACT_HEADERS,
    CONTACT_SHEET,
    MESSAGE_HEADERS,
    MESSAGE_SHEET,
    SNAPSHOT_SHEET,
    contacts_by_id,
    ensure_communication_sheets,
    latest_communicated_snapshot,
)


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


class _FakeRepository:
    def __init__(self, changes=None):
        self.path = "fixture.xlsx"
        self._lock = nullcontext()
        self._changes = dict(changes or {})
        self.ensure_calls: list[tuple[str, tuple[str, ...], str]] = []
        self.save_calls = 0
        self.record_calls: list[tuple[str, str]] = []

    def _ensure_sheet_table(self, sheet_name, headers, table_name):
        self.ensure_calls.append((sheet_name, tuple(headers), table_name))
        return bool(self._changes.pop(sheet_name, False))

    def save(self):
        self.save_calls += 1

    def _sheet_as_records(self, sheet_name, key_field):
        self.record_calls.append((sheet_name, key_field))
        return []


class CommunicationSchemaMigrationTests(unittest.TestCase):
    def test_no_save_when_all_communication_tables_are_current(self) -> None:
        repo = _FakeRepository()

        report = ensure_communication_sheets(repo)

        self.assertFalse(report.changed)
        self.assertEqual(
            report.migration_ids,
            (
                "communication.contacts.table.v1",
                "communication.batches.table.v1",
                "communication.messages.table.v1",
                "communication.snapshot.table.v1",
            ),
        )
        self.assertEqual(len(repo.ensure_calls), 4)
        self.assertEqual(repo.save_calls, 0)
        self.assertTrue(hasattr(repo, "_communication_schema_marker"))

    def test_one_save_when_one_or_more_tables_change(self) -> None:
        repo = _FakeRepository(
            {
                CONTACT_SHEET: True,
                SNAPSHOT_SHEET: True,
            }
        )

        report = ensure_communication_sheets(repo)

        self.assertTrue(report.changed)
        self.assertEqual(
            report.changed_migration_ids,
            (
                "communication.contacts.table.v1",
                "communication.snapshot.table.v1",
            ),
        )
        self.assertEqual(len(repo.ensure_calls), 4)
        self.assertEqual(repo.save_calls, 1)
        self.assertFalse(hasattr(repo, "_communication_schema_marker"))

    def test_changed_pass_requires_one_confirmation_then_uses_marker(self) -> None:
        repo = _FakeRepository({MESSAGE_SHEET: True})

        first = ensure_communication_sheets(repo)
        second = ensure_communication_sheets(repo)
        calls_after_confirmation = list(repo.ensure_calls)
        third = ensure_communication_sheets(repo)

        self.assertTrue(first.changed)
        self.assertFalse(second.changed)
        self.assertFalse(third.changed)
        self.assertEqual(len(calls_after_confirmation), 8)
        self.assertEqual(repo.ensure_calls, calls_after_confirmation)
        self.assertEqual(repo.save_calls, 1)

    def test_current_schema_uses_marker_on_second_pass(self) -> None:
        repo = _FakeRepository()

        first = ensure_communication_sheets(repo)
        calls_after_first = list(repo.ensure_calls)
        second = ensure_communication_sheets(repo)

        self.assertFalse(first.changed)
        self.assertFalse(second.changed)
        self.assertEqual(repo.ensure_calls, calls_after_first)
        self.assertEqual(repo.save_calls, 0)

    def test_header_shape_change_invalidates_schema_marker(self) -> None:
        repo = _FakeRepository()
        ensure_communication_sheets(repo)
        self.assertEqual(len(repo.ensure_calls), 4)

        MESSAGE_HEADERS.append("ChampTestMigration")
        try:
            ensure_communication_sheets(repo)
        finally:
            MESSAGE_HEADERS.remove("ChampTestMigration")

        self.assertEqual(len(repo.ensure_calls), 8)
        self.assertEqual(repo.save_calls, 0)

    def test_read_paths_do_not_save_when_schema_is_current(self) -> None:
        repo = _FakeRepository()

        contacts = contacts_by_id(repo)
        fingerprint, assignments = latest_communicated_snapshot(
            repo,
            date(2026, 8, 24),
        )

        self.assertEqual(contacts, {})
        self.assertEqual(fingerprint, "")
        self.assertEqual(assignments, [])
        self.assertEqual(repo.save_calls, 0)
        # First read checks four tables. The second read reuses the marker.
        self.assertEqual(len(repo.ensure_calls), 4)
        self.assertIn((CONTACT_SHEET, "PersonneCle"), repo.record_calls)
        self.assertIn((BATCH_SHEET, "IDLot"), repo.record_calls)

    def test_communication_ensure_has_no_unconditional_save(self) -> None:
        source = (APP / "communication_excel.py").read_text(encoding="utf-8")
        start = source.index("def ensure_communication_sheets(")
        end = source.index("\n\ndef contacts_by_id", start)
        ensure_source = source[start:end]

        self.assertIn("run_excel_schema_migrations(", ensure_source)
        self.assertIn("if report.changed:", ensure_source)
        self.assertIn("else:", ensure_source)
        self.assertIn("repo._communication_schema_marker = marker", ensure_source)
        self.assertNotIn("repo._ensure_sheet_table(", ensure_source)
        self.assertEqual(ensure_source.count("repo.save()"), 1)

    def test_contact_header_constant_is_unchanged(self) -> None:
        self.assertEqual(
            CONTACT_HEADERS,
            [
                "PersonneCle",
                "TypePersonne",
                "NomAffiche",
                "Courriel",
                "Actif",
                "DateModification",
            ],
        )


if __name__ == "__main__":
    unittest.main()
