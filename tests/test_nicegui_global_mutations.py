from __future__ import annotations

from pathlib import Path
import unittest


class NiceGUIGlobalMutationTests(unittest.TestCase):
    def _source(self, name: str) -> str:
        return (Path(__file__).resolve().parents[1] / "app" / name).read_text(
            encoding="utf-8"
        )

    def _offenders(self, token: str) -> list[str]:
        app_dir = Path(__file__).resolve().parents[1] / "app"
        return [
            path.name
            for path in sorted(app_dir.glob("*.py"))
            if token in path.read_text(encoding="utf-8")
        ]

    def test_scroll_area_factory_is_never_replaced_globally(self) -> None:
        offenders = sorted(
            set(self._offenders("ui.scroll_area =") + self._offenders("nicegui_ui.scroll_area ="))
        )
        self.assertEqual(offenders, [])

    def test_operational_select_overrides_use_context_managers(self) -> None:
        offenders = sorted(
            set(self._offenders("ui.select =") + self._offenders("nicegui_ui.select ="))
        )
        self.assertEqual(offenders, [])

        for filename in ("v16_refinements.py", "operational_planning_base_renderer.py"):
            renderer = self._source(filename)
            self.assertIn("ensure_scoped_ui(", renderer)
            self.assertIn('with scoped_ui.override_factory("select", select_proxy):', renderer)
            self.assertNotIn(".ui.select = select_proxy", renderer)

    def test_operational_scroll_uses_static_module_local_override(self) -> None:
        source = self._source("operational_planning_compat.py")
        self.assertIn('static_overrides={"scroll_area": _horizontal_container}', source)
        self.assertIn('OPERATIONAL_SCROLL_CLASS = "v18-operational-scroll"', source)
        self.assertIn(".schedule-grid", source)
        self.assertNotIn("original_scroll_area", source)
        self.assertNotIn("PlannerUI.render_planning =", source)

    def test_segment_parent_navigation_is_owned_by_explicit_editor(self) -> None:
        source = self._source("segment_editor_ui.py")
        self.assertIn('demand_select.props("append-icon=open_in_new")', source)
        self.assertIn("owner.open_edit_request_dialog(current_demand)", source)
        self.assertFalse(
            (Path(__file__).resolve().parents[1] / "app" / "segment_navigation_compat.py").exists()
        )

    def test_resource_class_precedence_is_an_explicit_compatibility_rule(self) -> None:
        source = self._source("resource_class_compat.py")
        self.assertIn('if "installation" in text or "installateur" in text:', source)
        self.assertIn('return "Installation"', source)
        self.assertIn("original_normalize(value)", source)


if __name__ == "__main__":
    unittest.main()
