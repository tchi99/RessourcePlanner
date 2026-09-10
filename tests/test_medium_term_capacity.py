from __future__ import annotations

from pathlib import Path
import unittest

from app import v16
from app.medium_term_capacity import _effort_class, _style_for_load


class MediumTermCapacityTests(unittest.TestCase):
    def test_capacity_signal_compares_planned_and_macro_without_adding_them(self) -> None:
        # 30 h planned + 30 h macro must remain a 30/40 exposure, not a fake 60/40 overload.
        style = _style_for_load(capacity=40, planned=30, projected=30)
        self.assertIn("#dcfce7", style)
        self.assertNotIn("#fee2e2", style)

    def test_capacity_signal_uses_larger_scenario_for_risk(self) -> None:
        self.assertIn(
            "#fee2e2",
            _style_for_load(capacity=40, planned=10, projected=48),
        )
        self.assertIn(
            "#fee2e2",
            _style_for_load(capacity=40, planned=48, projected=10),
        )

    def test_effort_uses_explicit_technician_class_when_available(self) -> None:
        effort = {"Équipe/Technicien attitré": "Alice"}
        self.assertEqual(
            _effort_class(effort, {"Alice": "Programmation"}, []),
            "Programmation",
        )

    def test_unassigned_effort_can_infer_one_consistent_linked_class(self) -> None:
        linked = [{"Technicien": "Alice"}, {"Technicien": "Bob"}]
        classes = {"Alice": "Programmation", "Bob": "Programmation"}
        self.assertEqual(
            _effort_class({}, classes, linked),
            "Programmation",
        )

    def test_mixed_or_unknown_linked_classes_stay_unclassified(self) -> None:
        mixed = [{"Technicien": "Alice"}, {"Technicien": "Bob"}]
        self.assertEqual(
            _effort_class(
                {},
                {"Alice": "Programmation", "Bob": "Installation"},
                mixed,
            ),
            v16.UNCLASSIFIED,
        )
        self.assertEqual(_effort_class({}, {}, []), v16.UNCLASSIFIED)

    def test_active_medium_term_renderer_uses_projected_capacity_wrapper(self) -> None:
        app_dir = Path(__file__).resolve().parents[1] / "app"
        source = (app_dir / "medium_term_renderer_compat.py").read_text(encoding="utf-8")
        self.assertIn("render_medium_term_with_projected_capacity", source)
        self.assertIn("register_medium_term_renderer(render_medium_term_with_projected_capacity)", source)

    def test_projection_module_keeps_planned_and_macro_labels_explicit(self) -> None:
        app_dir = Path(__file__).resolve().parents[1] / "app"
        source = (app_dir / "medium_term_capacity.py").read_text(encoding="utf-8")
        self.assertIn('text = f"P {planned:.0f}h\\nM {projected:.0f}h"', source)
        self.assertIn("exposure = max(planned, projected)", source)
        self.assertNotIn("planned + projected", source)


if __name__ == "__main__":
    unittest.main()
