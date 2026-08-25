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

    def test_v17_resource_row_is_only_a_compatibility_wrapper(self) -> None:
        source = (APP / "v17.py").read_text(encoding="utf-8")
        start = source.index("def _render_resource_row(")
        end = source.index("\ndef _render_planning(", start)
        wrapper = source[start:end]

        self.assertIn("ResourceRowBindings(", wrapper)
        self.assertIn("render_operational_planning_resource_row(", wrapper)
        self.assertNotIn("ui.", wrapper)
        self.assertNotIn("def _open_quick_allocation(", source)
        self.assertNotIn("open_operational_planning_cell_shift", source)


if __name__ == "__main__":
    unittest.main()
