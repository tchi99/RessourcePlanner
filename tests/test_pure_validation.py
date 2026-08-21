from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app import config
from app.pure_validation import load_validation_state, record_pure_cycle


class PureValidationTests(unittest.TestCase):
    def test_successes_accumulate_and_error_resets_consecutive_count(self) -> None:
        with TemporaryDirectory() as folder:
            path = Path(folder) / "validation.json"
            sample = {
                "engine": "pure",
                "status": "success",
                "total_seconds": 1.23456,
                "segment_count": 4,
                "allocation_output_count": 9,
            }

            first = record_pure_cycle(
                sample,
                path=path,
                now=datetime(2026, 8, 21, 16, 0, 0),
            )
            second = record_pure_cycle(
                sample,
                path=path,
                now=datetime(2026, 8, 21, 16, 1, 0),
            )
            failed = record_pure_cycle(
                {
                    "engine": "pure",
                    "status": "error",
                    "error_type": "RuntimeError",
                    "total_seconds": 0.5,
                },
                path=path,
                now=datetime(2026, 8, 21, 16, 2, 0),
            )

            self.assertEqual(first["pure_success_count"], 1)
            self.assertEqual(second["pure_success_count"], 2)
            self.assertEqual(second["consecutive_pure_successes"], 2)
            self.assertEqual(failed["pure_error_count"], 1)
            self.assertEqual(failed["consecutive_pure_successes"], 0)
            self.assertEqual(failed["last_error_type"], "RuntimeError")
            self.assertEqual(failed["first_pure_success_at"], "2026-08-21T16:00:00")
            self.assertEqual(failed["last_pure_success_at"], "2026-08-21T16:01:00")

    def test_non_pure_sample_does_not_create_validation_evidence(self) -> None:
        with TemporaryDirectory() as folder:
            path = Path(folder) / "validation.json"
            state = record_pure_cycle(
                {"engine": "legacy", "status": "success"},
                path=path,
            )

            self.assertFalse(path.exists())
            self.assertEqual(state, load_validation_state(path))
            self.assertEqual(state["pure_success_count"], 0)

    def test_journal_contains_only_technical_fields(self) -> None:
        with TemporaryDirectory() as folder:
            path = Path(folder) / "validation.json"
            record_pure_cycle(
                {
                    "engine": "pure",
                    "status": "success",
                    "total_seconds": 2.0,
                    "segment_count": 2,
                    "allocation_output_count": 3,
                    "project_name": "Must not persist",
                    "technician": "Must not persist",
                    "location": "Must not persist",
                },
                path=path,
            )
            raw = json.loads(path.read_text(encoding="utf-8"))

            self.assertNotIn("project_name", raw)
            self.assertNotIn("technician", raw)
            self.assertNotIn("location", raw)

    def test_old_engine_mode_key_is_ignored_and_removed_on_next_config_save(self) -> None:
        with TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "app_config.json"
            workbook = root / "Production.xlsx"
            path.write_text(
                json.dumps(
                    {
                        "workbook": str(workbook),
                        "refresh_seconds": 5,
                        "planning_engine_mode": "legacy",
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(config, "CONFIG_PATH", path):
                loaded = config.load_config()
                config.save_workbook_path(loaded.workbook)

            raw = json.loads(path.read_text(encoding="utf-8"))
            self.assertFalse(hasattr(loaded, "planning_engine_mode"))
            self.assertNotIn("planning_engine_mode", raw)
            self.assertEqual(raw["workbook"], str(workbook))
            self.assertEqual(raw["refresh_seconds"], 5)
            self.assertEqual(raw["host"], "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
