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

    def test_sorting_compat_uses_resource_management_owner(self) -> None:
        source = self._source("operational_planning_sorting_compat.py")

        self.assertIn("resource_management._resource_order_map", source)
        self.assertNotIn("v17_refinements", source)
        ast.parse(source)

    def test_v17_v171_shims_and_bridge_are_physically_removed(self) -> None:
        for name in (
            "v17_refinements.py",
            "v17_sort_fix.py",
            "v171_performance.py",
            "v171_local_preferences.py",
            "resource_local_preferences_compat.py",
        ):
            self.assertFalse((APP / name).exists(), name)

    def test_no_application_module_imports_retired_v17_v171_modules(self) -> None:
        retired = {
            "v17",
            "v17_refinements",
            "v17_sort_fix",
            "v171_performance",
            "v171_local_preferences",
            "resource_local_preferences_compat",
        }
        offenders: list[str] = []

        for path in APP.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".")[-1] in retired:
                            offenders.append(f"{path.relative_to(APP)}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = (node.module or "").split(".")[-1]
                    if module in retired:
                        offenders.append(
                            f"{path.relative_to(APP)}: from {node.module} import ..."
                        )
                    if node.module is None:
                        for alias in node.names:
                            if alias.name in retired:
                                offenders.append(
                                    f"{path.relative_to(APP)}: from . import {alias.name}"
                                )

        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_runtime_composition_installs_stable_adapters_directly(self) -> None:
        source = self._source("runtime_composition.py")

        self.assertIn('CompositionStep("runtime_performance", "compatibility")', source)
        self.assertIn('CompositionStep("resource_local_preferences", "compatibility")', source)
        self.assertIn(
            "from .resource_local_preferences import install_resource_local_preferences",
            source,
        )
        self.assertIn(
            '("resource_local_preferences", install_resource_local_preferences)',
            source,
        )
        self.assertNotIn("resource_local_preferences_compat", source)
        self.assertNotIn('CompositionStep("v171_performance"', source)
        self.assertNotIn('CompositionStep("v171_local_preferences"', source)


if __name__ == "__main__":
    unittest.main()
