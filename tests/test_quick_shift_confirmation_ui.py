from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


class QuickShiftConfirmationUiTests(unittest.TestCase):
    def test_quick_shift_mode_exposes_explicit_confirmation(self) -> None:
        source = (APP / "quick_shift_ui.py").read_text(encoding="utf-8")

        self.assertIn('label="Confirmation du quart rapide"', source)
        self.assertIn("CONFIRMATION_TENTATIVE", source)
        self.assertIn("CONFIRMATION_CONFIRMED", source)
        self.assertIn("quick_confirmation.value", source)
        self.assertIn("confirmation=str(", source)

    def test_existing_segment_mode_can_inherit_or_override_shift_confirmation(self) -> None:
        source = (APP / "quick_shift_ui.py").read_text(encoding="utf-8")

        self.assertIn('INHERIT_CONFIRMATION = "__inherit__"', source)
        self.assertIn("Héritée du segment / de la demande", source)
        self.assertIn('label="Confirmation du quart"', source)
        self.assertIn("Confirmation héritée actuelle", source)
        self.assertIn("confirmation_override = None", source)
        self.assertIn("confirmation_override,", source)

    def test_quick_shift_ensures_segment_confirmation_compatibility_column(self) -> None:
        source = (APP / "quick_shift_ui.py").read_text(encoding="utf-8")

        self.assertIn(
            "ensure_segment_fields(repo, [SEGMENT_ORIGIN_FIELD, SEGMENT_CONFIRMATION_FIELD])",
            source,
        )


if __name__ == "__main__":
    unittest.main()
