from __future__ import annotations

from pathlib import Path
import unittest


class OperationalPlanningOrchestratorExtractionTests(unittest.TestCase):
    def test_orchestrator_is_non_versioned_and_composes_stable_renderers(self) -> None:
        app_dir = Path(__file__).resolve().parents[1] / "app"
        source = (app_dir / "operational_planning_orchestrator.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("class OperationalPlanningBindings", source)
        self.assertIn("def render_operational_planning(", source)
        self.assertIn("render_operational_planning_header_filters(", source)
        self.assertIn("render_operational_planning_work_sections(", source)
        self.assertIn("group_operational_planning_resources(", source)
        self.assertIn("render_operational_planning_grid(", source)
        for version in ("v13", "v14", "v15", "v16", "v17", "v18"):
            self.assertNotIn(f"from . import {version}", source)
            self.assertNotIn(f"from .{version}", source)

    def test_v17_no_longer_contains_a_planning_renderer(self) -> None:
        app_dir = Path(__file__).resolve().parents[1] / "app"
        source = (app_dir / "v17.py").read_text(encoding="utf-8")

        self.assertNotIn("def _render_planning(", source)
        self.assertNotIn("render_operational_planning(", source)
        self.assertNotIn("operational_planning_bindings", source)

    def test_v17_refinement_targets_stable_filter_ui_and_orchestrator(self) -> None:
        app_dir = Path(__file__).resolve().parents[1] / "app"
        source = (app_dir / "v17_refinements.py").read_text(encoding="utf-8")

        self.assertIn(
            "from . import operational_planning_header_filters as header_filters_module",
            source,
        )
        self.assertIn("ensure_scoped_ui(\n        header_filters_module,", source)
        self.assertIn("render_operational_planning(", source)
        self.assertIn("bindings=operational_planning_bindings()", source)
        self.assertNotIn("v17._render_planning", source)
        self.assertNotIn("v16, v16_refinements, v17", source)


if __name__ == "__main__":
    unittest.main()
