from __future__ import annotations

from datetime import date
from pathlib import Path
import unittest

from app.operational_planning_cell_context import (
    CellContextBindings,
    OperationalPlanningCellContext,
)


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


class OperationalPlanningCellContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.day = date(2026, 8, 25)
        self.segments = [
            {
                "IDSegment": "SEG-1",
                "NumeroProjet": "5001",
                "Technicien": "Mathieu",
                "DateDebut": self.day,
                "DateFin": self.day,
                "HeuresPrevues": 8,
                "Statut": "Planifié",
                "Priorite": "Normale",
                "CompetenceRequise": "PLC",
            },
            {
                "IDSegment": "SEG-FULL",
                "NumeroProjet": "5002",
                "Technicien": "Mathieu",
                "DateDebut": self.day,
                "DateFin": self.day,
                "HeuresPrevues": 2,
                "Statut": "Planifié",
                "Priorite": "Normale",
            },
            {
                "IDSegment": "SEG-OTHER",
                "NumeroProjet": "5003",
                "Technicien": "Alex",
                "DateDebut": self.day,
                "DateFin": self.day,
                "HeuresPrevues": 4,
                "Statut": "Planifié",
                "Priorite": "Normale",
            },
        ]
        self.allocations = [
            {
                "IDAllocation": "A1",
                "IDSegment": "SEG-1",
                "Technicien": "Mathieu",
                "Date": self.day,
                "Heures": 3,
                "Verrouillee": "Oui",
                "HorsHoraire": "Non",
            },
            {
                "IDAllocation": "A2",
                "IDSegment": "SEG-1",
                "Technicien": "Mathieu",
                "Date": self.day,
                "Heures": 2,
                "Verrouillee": "Non",
                "HorsHoraire": "Non",
            },
            {
                "IDAllocation": "A3",
                "IDSegment": "SEG-1",
                "Technicien": "Mathieu",
                "Date": self.day,
                "Heures": 1,
                "Verrouillee": "Oui",
                "HorsHoraire": "Oui",
            },
            {
                "IDAllocation": "A-MISSING",
                "IDSegment": "SEG-1",
                "Technicien": "Mathieu",
                "Date": self.day,
                "Heures": 5,
                "Verrouillee": "Oui",
                "Missing": True,
            },
            {
                "IDAllocation": "A-FULL",
                "IDSegment": "SEG-FULL",
                "Technicien": "Mathieu",
                "Date": self.day,
                "Heures": 2,
                "Verrouillee": "Oui",
                "HorsHoraire": "Non",
            },
        ]
        self.context = OperationalPlanningCellContext(
            CellContextBindings(
                segment_records=lambda repo, include_cancelled=False: list(self.segments),
                allocation_records=lambda repo: list(self.allocations),
                is_missing_allocation=lambda row: bool(row.get("Missing")),
                truthy=lambda value: str(value or "").lower() in {"oui", "true", "1"},
                number=lambda value: float(value or 0),
                availability_hours=lambda repo, technician, day: 8.0,
                parse_date=lambda value: value if isinstance(value, date) else None,
                segment_dates=lambda row: (row.get("DateDebut"), row.get("DateFin")),
                resource_competence_map=lambda repo: {"Mathieu": {"plc"}},
                normalized_text=lambda value: str(value or "").strip().lower(),
            )
        )

    def test_locked_hours_and_validation_ignore_unlocked_and_missing_rows(self) -> None:
        self.assertEqual(self.context.locked_hours(None, "SEG-1"), 4.0)
        self.assertEqual(
            self.context.locked_hours(None, "SEG-1", exclude_allocation="A1"),
            1.0,
        )
        self.context.validate_locked_total(None, "SEG-1", 4)
        with self.assertRaises(ValueError):
            self.context.validate_locked_total(None, "SEG-1", 4.1)

    def test_day_standard_load_excludes_overtime_and_missing_rows(self) -> None:
        capacity, used, free = self.context.day_standard_load(
            None,
            "Mathieu",
            self.day,
        )
        self.assertEqual((capacity, used, free), (8.0, 7.0, 1.0))

    def test_eligible_segments_require_window_resource_and_remaining_hours(self) -> None:
        rows = self.context.eligible_segments_for_cell(
            None,
            "Mathieu",
            self.day,
        )
        self.assertEqual([row["IDSegment"] for row in rows], ["SEG-1"])

    def test_skill_message_uses_shared_resource_profile_logic(self) -> None:
        message, match = self.context.skill_message(None, "Mathieu", self.segments[0])
        self.assertTrue(match)
        self.assertIn("PLC", message)

        message, match = self.context.skill_message(None, "Alex", self.segments[0])
        self.assertFalse(match)
        self.assertIn("Attention", message)

    def test_architecture_removes_quick_shift_dependency_on_v17(self) -> None:
        context_source = (APP / "operational_planning_cell_context.py").read_text(
            encoding="utf-8"
        )
        quick_shift_source = (APP / "quick_shift_ui.py").read_text(encoding="utf-8")
        v17_source = (APP / "v17.py").read_text(encoding="utf-8")
        drop_compat_source = (
            APP / "operational_planning_drop_handler_compat.py"
        ).read_text(encoding="utf-8")

        for versioned in ("v13", "v14", "v15", "v16", "v17"):
            self.assertNotIn(f"from . import {versioned}", context_source)
            self.assertNotIn(f"from .{versioned}", context_source)

        self.assertNotIn("from . import v15_engine, v17", quick_shift_source)
        self.assertNotIn("v17._", quick_shift_source)
        for helper in (
            "_segment_by_id",
            "_actual_allocations",
            "_locked_hours",
            "_validate_locked_total",
            "_skill_message",
            "_day_standard_load",
            "_eligible_segments_for_cell",
        ):
            self.assertNotIn(f"def {helper}(", v17_source)
        self.assertIn("cell_context.validate_locked_total(", v17_source)
        self.assertNotIn("def _skill_message(", drop_compat_source)
        self.assertNotIn("def _segment_by_id(", drop_compat_source)


if __name__ == "__main__":
    unittest.main()
