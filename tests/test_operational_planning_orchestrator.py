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

    def test_v17_render_entry_point_is_only_a_compatibility_wrapper(self) -> None:
        app_dir = Path(__file__).resolve().parents[1] / "app"
        source = (app_dir / "v17.py").read_text(encoding="utf-8")
        start = source.index("def _render_planning(")
        end = source.index("\ndef install_v17_features", start)
        wrapper = source[start:end]

        self.assertIn("render_operational_planning(", wrapper)
        self.assertIn("operational_planning_bindings()", wrapper)
        self.assertNotIn("week_days(", wrapper)
        self.assertNotIn("segment_records(", wrapper)
        self.assertNotIn("allocation_records(", wrapper)
        self.assertNotIn("render_operational_planning_grid(", wrapper)
        self.assertNotIn("group_operational_planning_resources(", wrapper)


if __name__ == "__main__":
    unittest.main()
