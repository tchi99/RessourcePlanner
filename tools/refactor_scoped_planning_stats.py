from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
TESTS = ROOT / "tests"


def update_v17() -> None:
    path = APP / "v17.py"
    source = path.read_text(encoding="utf-8")
    old_signature = "def _render_planning(self: ui_module.PlannerUI) -> None:\n"
    new_signature = (
        "def _render_planning(\n"
        "    self: ui_module.PlannerUI,\n"
        "    *,\n"
        "    weekly_stats_provider: Any | None = None,\n"
        ") -> None:\n"
    )
    if old_signature not in source:
        raise RuntimeError("v17 planning signature not found")
    source = source.replace(old_signature, new_signature, 1)

    old_stats = "    week_stats = v16._weekly_resource_stats(self.repo, self.current_week)\n"
    new_stats = (
        "    stats_provider = weekly_stats_provider or v16._weekly_resource_stats\n"
        "    week_stats = stats_provider(self.repo, self.current_week)\n"
    )
    if old_stats not in source:
        raise RuntimeError("v17 weekly stats call not found")
    source = source.replace(old_stats, new_stats, 1)
    path.write_text(source, encoding="utf-8")


def update_v17_refinements() -> None:
    path = APP / "v17_refinements.py"
    source = path.read_text(encoding="utf-8")
    old_signature = "def _render_planning(self: ui_module.PlannerUI) -> None:\n"
    new_signature = (
        "def _render_planning(\n"
        "    self: ui_module.PlannerUI,\n"
        "    *,\n"
        "    weekly_stats_provider: Any | None = None,\n"
        ") -> None:\n"
    )
    if old_signature not in source:
        raise RuntimeError("v17_refinements planning signature not found")
    source = source.replace(old_signature, new_signature, 1)

    old_call = "        v17._render_planning(self)\n"
    new_call = (
        "        v17._render_planning(\n"
        "            self,\n"
        "            weekly_stats_provider=weekly_stats_provider,\n"
        "        )\n"
    )
    if old_call not in source:
        raise RuntimeError("v17_refinements renderer call not found")
    source = source.replace(old_call, new_call, 1)
    path.write_text(source, encoding="utf-8")


def update_sort_fix() -> None:
    path = APP / "v17_sort_fix.py"
    source = path.read_text(encoding="utf-8")
    old = '''        v16._weekly_resource_stats = ranked_stats\n        try:\n            base_render(self)\n        finally:\n            v16._weekly_resource_stats = original_weekly_stats\n'''
    new = '''        base_render(self, weekly_stats_provider=ranked_stats)\n'''
    if old not in source:
        raise RuntimeError("v17_sort_fix process-wide stats override not found")
    source = source.replace(old, new, 1)
    path.write_text(source, encoding="utf-8")


def add_tests() -> None:
    path = TESTS / "test_operational_renderer_architecture.py"
    content = '''from __future__ import annotations\n\nfrom pathlib import Path\nimport unittest\n\n\nROOT = Path(__file__).resolve().parents[1]\nAPP = ROOT / "app"\n\n\nclass OperationalRendererArchitectureTests(unittest.TestCase):\n    def _source(self, name: str) -> str:\n        return (APP / name).read_text(encoding="utf-8")\n\n    def test_v17_accepts_explicit_weekly_stats_provider(self) -> None:\n        source = self._source("v17.py")\n        self.assertIn("weekly_stats_provider: Any | None = None", source)\n        self.assertIn("stats_provider = weekly_stats_provider or v16._weekly_resource_stats", source)\n        self.assertIn("week_stats = stats_provider(self.repo, self.current_week)", source)\n\n    def test_refinement_forwards_provider_without_global_mutation(self) -> None:\n        source = self._source("v17_refinements.py")\n        self.assertIn("weekly_stats_provider: Any | None = None", source)\n        self.assertIn("weekly_stats_provider=weekly_stats_provider", source)\n\n    def test_sort_fix_injects_ranked_stats_without_replacing_module_function(self) -> None:\n        source = self._source("v17_sort_fix.py")\n        self.assertIn("base_render(self, weekly_stats_provider=ranked_stats)", source)\n        self.assertNotIn("v16._weekly_resource_stats = ranked_stats", source)\n        self.assertNotIn("v16._weekly_resource_stats = original_weekly_stats", source)\n\n\nif __name__ == "__main__":\n    unittest.main()\n'''
    if path.exists():
        raise RuntimeError("operational renderer architecture test already exists")
    path.write_text(content, encoding="utf-8")


def main() -> None:
    update_v17()
    update_v17_refinements()
    update_sort_fix()
    add_tests()


if __name__ == "__main__":
    main()
