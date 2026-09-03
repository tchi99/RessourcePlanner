from __future__ import annotations

from pathlib import Path
import unittest

from app.shift_confirmation_ui import allocation_confirmation


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


class ShiftConfirmationUiTests(unittest.TestCase):
    def test_shift_confirmation_inherits_request_when_no_override(self) -> None:
        self.assertEqual(
            allocation_confirmation({}, {"Confirmation": "Tentative"}),
            "Tentative",
        )
        self.assertEqual(
            allocation_confirmation({}, {"Confirmation": "Confirmée"}),
            "Confirmée",
        )

    def test_shift_confirmation_override_wins_over_request(self) -> None:
        self.assertEqual(
            allocation_confirmation(
                {"Confirmation": "Tentative"},
                {"Confirmation": "Confirmée"},
            ),
            "Tentative",
        )
        self.assertEqual(
            allocation_confirmation(
                {"Confirmation": "Confirmée"},
                {"Confirmation": "Tentative"},
            ),
            "Confirmée",
        )

    def test_dialog_exposes_inherit_tentative_and_confirmed_choices(self) -> None:
        source = (APP / "shift_confirmation_ui.py").read_text(encoding="utf-8")

        self.assertIn('label="Confirmation du quart"', source)
        self.assertIn("Héritée du segment / de la demande", source)
        self.assertIn("CONFIRMATION_TENTATIVE", source)
        self.assertIn("CONFIRMATION_CONFIRMED", source)
        self.assertIn("selected_confirmation()", source)

    def test_excel_adapter_persists_nullable_shift_override(self) -> None:
        source = (
            APP / "infrastructure" / "excel" / "command_adapters.py"
        ).read_text(encoding="utf-8")

        self.assertIn('ALLOCATION_CONFIRMATION_FIELD = "Confirmation"', source)
        self.assertIn("_set_allocation_confirmation", source)
        self.assertIn("confirmation: str | None = None", source)

    def test_operational_grid_uses_effective_shift_confirmation(self) -> None:
        source = (APP / "operational_planning_resource_row.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("allocation_confirmation:", source)
        self.assertIn("bindings.allocation_confirmation(", source)
        self.assertIn('effective_confirmation == "Tentative"', source)


if __name__ == "__main__":
    unittest.main()
