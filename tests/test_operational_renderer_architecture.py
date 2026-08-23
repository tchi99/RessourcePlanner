from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


class OperationalRendererArchitectureTests(unittest.TestCase):
    def _source(self, name: str) -> str:
        return (APP / name).read_text(encoding="utf-8")

    def test_v17_accepts_explicit_weekly_stats_provider(self) -> None:
        source = self._source("v17.py")
        self.assertIn("weekly_stats_provider: Any | None = None", source)
        self.assertIn("stats_provider = weekly_stats_provider or v16._weekly_resource_stats", source)
        self.assertIn("week_stats = stats_provider(self.repo, self.current_week)", source)

    def test_refinement_forwards_provider_without_global_mutation(self) -> None:
        source = self._source("v17_refinements.py")
        self.assertIn("weekly_stats_provider: Any | None = None", source)
        self.assertIn("weekly_stats_provider=weekly_stats_provider", source)

    def test_sort_fix_injects_ranked_stats_without_replacing_module_function(self) -> None:
        source = self._source("v17_sort_fix.py")
        self.assertIn("base_render(self, weekly_stats_provider=ranked_stats)", source)
        self.assertNotIn("v16._weekly_resource_stats = ranked_stats", source)
        self.assertNotIn("v16._weekly_resource_stats = original_weekly_stats", source)


if __name__ == "__main__":
    unittest.main()
