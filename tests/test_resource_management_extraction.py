from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


class ResourceManagementExtractionTests(unittest.TestCase):
    def test_resource_management_owns_v17_resource_behaviors(self) -> None:
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

        self.assertIn("legacy_overrides._manual_order_dialog(self)", source)
        self.assertIn("legacy_overrides._new_resource_dialog(self)", source)
        ast.parse(source)

    def test_v17_refinements_is_only_a_temporary_shim(self) -> None:
        source = (APP / "v17_refinements.py").read_text(encoding="utf-8")

        self.assertIn("Compatibility shim", source)
        self.assertIn("from .resource_management_compat import (", source)
        self.assertIn("install_resource_management_compat()", source)
        self.assertNotIn("from nicegui import ui", source)
        self.assertNotIn("def _new_resource_dialog(", source)
        self.assertNotIn("def _manual_order_dialog(", source)
        self.assertNotIn("ExcelRepository.technicians =", source)
        ast.parse(source)


if __name__ == "__main__":
    unittest.main()
