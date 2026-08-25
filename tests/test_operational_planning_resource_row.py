from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


class OperationalPlanningResourceRowArchitectureTests(unittest.TestCase):
    def test_extracted_resource_row_has_no_direct_versioned_imports(self) -> None:
        source = (APP / "operational_planning_resource_row.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("class ResourceRowBindings", source)
        self.assertIn("def render_operational_planning_resource_row(", source)
        self.assertIn("open_operational_planning_cell_shift(", source)
        for versioned in ("v13", "v14", "v15", "v16", "v17"):
            self.assertNotIn(f"from . import {versioned}", source)
            self.assertNotIn(f"from .{versioned}", source)

    def test_v17_calls_extracted_resource_row_without_local_wrapper(self) -> None:
        source = (APP / "v17.py").read_text(encoding="utf-8")

        self.assertNotIn("def _render_resource_row(", source)
        self.assertNotIn("ResourceRowBindings(", source)
        self.assertNotIn("def _make_draggable(", source)
        self.assertNotIn("def _make_drop_zone(", source)
        self.assertIn("row_bindings = operational_planning_resource_row_bindings()", source)
        self.assertIn("render_operational_planning_resource_row(", source)
        self.assertIn("bindings=row_bindings", source)

    def test_legacy_bindings_are_isolated_in_explicit_compatibility_module(self) -> None:
        source = (APP / "operational_planning_resource_row_compat.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("def operational_planning_resource_row_bindings(", source)
        self.assertIn("ResourceRowBindings(", source)
        self.assertIn("make_drop_zone=make_drop_zone", source)
        self.assertIn("make_draggable=make_draggable", source)
        self.assertIn("v13", source)
        self.assertIn("v15", source)
        self.assertIn("v16", source)


if __name__ == "__main__":
    unittest.main()
