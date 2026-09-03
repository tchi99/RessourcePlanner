from __future__ import annotations

from pathlib import Path
import unittest

from app.operational_shift_editor_compat import (
    allocation_confirmation,
    demand_confirmation,
)


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


class V1ShiftConfirmationTests(unittest.TestCase):
    def test_shift_without_override_inherits_request_confirmation(self) -> None:
        self.assertEqual(
            allocation_confirmation({}, {"Confirmation": "Tentative"}),
            "Tentative",
        )
        self.assertEqual(
            allocation_confirmation({}, {"Confirmation": "Confirmée"}),
            "Confirmée",
        )

    def test_explicit_shift_confirmation_overrides_request(self) -> None:
        self.assertEqual(
            allocation_confirmation(
                {"Confirmation": "Confirmée"},
                {"Confirmation": "Tentative"},
            ),
            "Confirmée",
        )
        self.assertEqual(
            allocation_confirmation(
                {"Confirmation": "Tentative"},
                {"Confirmation": "Confirmée"},
            ),
            "Tentative",
        )

    def test_invalid_legacy_values_fail_safe_to_request_or_confirmed(self) -> None:
        self.assertEqual(demand_confirmation({"Confirmation": "inconnu"}), "Confirmée")
        self.assertEqual(
            allocation_confirmation(
                {"Confirmation": "inconnu"},
                {"Confirmation": "Tentative"},
            ),
            "Tentative",
        )

    def test_editor_exposes_confirmation_and_routes_it_to_manual_mutation(self) -> None:
        source = (APP / "operational_shift_editor_compat.py").read_text(encoding="utf-8")
        self.assertIn('label="Confirmation du quart"', source)
        self.assertIn("selected_confirmation", source)
        self.assertIn("v15_engine.update_manual_allocation(", source)
        self.assertIn("v15_engine.create_manual_allocation(", source)

    def test_stable_resource_row_uses_effective_shift_confirmation(self) -> None:
        source = (APP / "operational_planning_resource_row.py").read_text(encoding="utf-8")
        compat = (APP / "operational_planning_resource_row_compat.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("allocation_confirmation:", source)
        self.assertIn("bindings.allocation_confirmation(", source)
        self.assertIn("allocation_confirmation=allocation_confirmation", compat)
        self.assertIn("open_allocation_dialog=open_allocation_dialog", compat)


if __name__ == "__main__":
    unittest.main()
