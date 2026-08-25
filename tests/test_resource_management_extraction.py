from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


class ResourceManagementExtractionTests(unittest.TestCase):
    def test_resource_management_owns_resource_behaviors_directly(self) -> None:
        source = (APP / "resource_management_compat.py").read_text(encoding="utf-8")

        for token in (
            "RESOURCE_ORDER_FIELD = \"Ordre\"",
            "def _resource_order_map(",
            "def _update_resource_profile_extended(",
            "def _new_resource_dialog(",
            "def _manual_order_dialog(",
            "def _render_resources(",
            "def technicians_with_profiles(",
            "def install_resource_management_compat(",
        ):
            self.assertIn(token, source)

        self.assertIn("on_click=lambda: _manual_order_dialog(self)", source)
        self.assertIn("on_click=lambda: _new_resource_dialog(self)", source)
        self.assertNotIn("legacy_overrides", source)
        self.assertNotIn("v17_refinements", source)
        ast.parse(source)

    def test_v17_resource_shims_are_physically_removed(self) -> None:
        self.assertFalse((APP / "v17_refinements.py").exists())
        self.assertFalse((APP / "v17_sort_fix.py").exists())


if __name__ == "__main__":
    unittest.main()
