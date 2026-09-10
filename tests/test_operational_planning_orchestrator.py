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

    def test_schedulable_resources_are_scoped_to_displayed_week(self) -> None:
        app_dir = Path(__file__).resolve().parents[1] / "app"
        source = (app_dir / "operational_planning_orchestrator.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("days = bindings.week_days(owner.current_week)", source)
        self.assertIn(
            "bindings.schedulable_technicians(owner.repo, days[0], days[-1])",
            source,
        )

    def test_v17_modules_are_retired(self) -> None:
        app_dir = Path(__file__).resolve().parents[1] / "app"
        for filename in ("v17.py", "v17_refinements.py", "v17_sort_fix.py"):
            self.assertFalse((app_dir / filename).exists(), filename)

    def test_stable_base_renderer_targets_orchestrator_with_explicit_bindings(self) -> None:
        app_dir = Path(__file__).resolve().parents[1] / "app"
        source = (app_dir / "operational_planning_base_renderer.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("render_operational_planning(", source)
        self.assertIn("bindings=bindings", source)
        self.assertIn("weekly_stats_provider=weekly_stats_provider", source)
        self.assertNotIn("v17_refinements", source)


if __name__ == "__main__":
    unittest.main()
