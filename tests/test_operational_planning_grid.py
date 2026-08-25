from __future__ import annotations

from pathlib import Path
import unittest


class OperationalPlanningGridExtractionTests(unittest.TestCase):
    def test_grid_renderer_is_non_versioned(self) -> None:
        app_dir = Path(__file__).resolve().parents[1] / "app"
        source = (app_dir / "operational_planning_grid.py").read_text(encoding="utf-8")

        self.assertIn("def render_operational_planning_grid(", source)
        self.assertIn("render_operational_planning_resource_row(", source)
        self.assertIn("ordered_resource_group_names(", source)
        self.assertIn("resource_group_totals(", source)
        for version in ("v13", "v14", "v15", "v16", "v17", "v18"):
            self.assertNotIn(f"from . import {version}", source)
            self.assertNotIn(f"from .{version}", source)

    def test_orchestrator_delegates_the_complete_grid(self) -> None:
        app_dir = Path(__file__).resolve().parents[1] / "app"
        source = (app_dir / "operational_planning_orchestrator.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("render_operational_planning_grid(", source)
        self.assertNotIn("ui.scroll_area(", source)
        self.assertNotIn("ui.expansion(", source)
        self.assertNotIn("ui.grid(columns=8)", source)
        self.assertNotIn("render_operational_planning_resource_row(", source)
        self.assertNotIn("ordered_resource_group_names(", source)
        self.assertNotIn("resource_group_totals(", source)


if __name__ == "__main__":
    unittest.main()
