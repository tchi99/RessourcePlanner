from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


class OperationalRendererArchitectureTests(unittest.TestCase):
    def _source(self, name: str) -> str:
        return (APP / name).read_text(encoding="utf-8")

    def test_orchestrator_accepts_explicit_weekly_stats_provider(self) -> None:
        source = self._source("operational_planning_orchestrator.py")
        self.assertIn("weekly_stats_provider: Callable", source)
        self.assertIn("stats_provider = weekly_stats_provider or bindings.weekly_resource_stats", source)
        self.assertIn("week_stats = stats_provider(owner.repo, owner.current_week)", source)
        self.assertFalse((APP / "v17.py").exists())

    def test_stable_base_renderer_forwards_provider_and_bindings(self) -> None:
        source = self._source("operational_planning_base_renderer.py")

        self.assertIn("weekly_stats_provider: Any | None = None", source)
        self.assertIn("weekly_stats_provider=weekly_stats_provider", source)
        self.assertIn("bindings=bindings", source)
        self.assertIn("render_operational_planning(", source)
        self.assertFalse((APP / "v17_refinements.py").exists())

    def test_stable_sorting_composes_ranked_stats_without_retired_shim(self) -> None:
        stable = self._source("operational_planning_sorting.py")
        compat = self._source("operational_planning_sorting_compat.py")

        self.assertIn("def rank_weekly_stats(", stable)
        self.assertIn("compose_operational_planning_renderer(", compat)
        self.assertIn("base_render=base_render", compat)
        self.assertIn("render_operational_planning_base(", compat)
        self.assertIn("rank_weekly_stats=ranked_weekly_stats", compat)
        self.assertNotIn("v16._weekly_resource_stats =", compat)
        self.assertNotIn("v17_refinements", compat)
        self.assertFalse((APP / "v17_sort_fix.py").exists())


if __name__ == "__main__":
    unittest.main()
