from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


class V171AdapterExtractionTests(unittest.TestCase):
    def _source(self, name: str) -> str:
        return (APP / name).read_text(encoding="utf-8")

    def test_runtime_performance_targets_stable_boundaries(self) -> None:
        source = self._source("runtime_performance_compat.py")

        self.assertIn("resource_management._order_number", source)
        self.assertIn("planning_sorting.alpha_key", source)
        self.assertIn("sorting_compat.move_manual_resource", source)
        self.assertIn("drop_handler_module._split_allocation", source)
        self.assertNotIn("v17_refinements", source)
        self.assertNotIn("v17_sort_fix", source)
        ast.parse(source)

    def test_local_preferences_targets_stable_boundaries(self) -> None:
        source = self._source("resource_local_preferences.py")

        self.assertIn("resource_management._resource_order_map", source)
        self.assertIn("planning_sorting.alpha_key", source)
        self.assertIn("sorting_compat.move_manual_resource", source)
        self.assertNotIn("v17_refinements", source)
        self.assertNotIn("v17_sort_fix", source)
        ast.parse(source)

    def test_only_bridge_mentions_remaining_v17_shims(self) -> None:
        bridge = self._source("resource_local_preferences_compat.py")
        self.assertIn("legacy_resource_shim", bridge)
        self.assertIn("legacy_sort_shim", bridge)
        self.assertIn("Temporary bridge only", bridge)
        ast.parse(bridge)

    def test_v171_modules_are_shims_only(self) -> None:
        performance = self._source("v171_performance.py")
        preferences = self._source("v171_local_preferences.py")

        self.assertIn("Compatibility shim", performance)
        self.assertIn("install_runtime_performance_compat()", performance)
        self.assertNotIn("from nicegui import ui", performance)
        self.assertIn("Compatibility shim", preferences)
        self.assertIn("install_resource_local_preferences_compat()", preferences)
        self.assertNotIn("from nicegui import ui", preferences)
        ast.parse(performance)
        ast.parse(preferences)

    def test_runtime_composition_no_longer_installs_v171_steps(self) -> None:
        source = self._source("runtime_composition.py")

        self.assertIn('CompositionStep("runtime_performance", "compatibility")', source)
        self.assertIn('CompositionStep("resource_local_preferences", "compatibility")', source)
        self.assertNotIn('CompositionStep("v171_performance"', source)
        self.assertNotIn('CompositionStep("v171_local_preferences"', source)


if __name__ == "__main__":
    unittest.main()
