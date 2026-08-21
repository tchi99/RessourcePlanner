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

    def test_legacy_select_assignments_are_limited_and_scoped_before_render(self) -> None:
        # The two historical renderers still use save/assign/restore syntax. They no
        # longer point at process-wide nicegui.ui: operational_planning_compat installs
        # a ContextVar-backed facade for both modules before any page is rendered.
        offenders = sorted(
            set(self._offenders("ui.select =") + self._offenders("nicegui_ui.select ="))
        )
        self.assertEqual(offenders, ["v16_refinements.py", "v17_refinements.py"])

        setup = self._source("operational_planning_compat.py")
        self.assertIn("ensure_scoped_ui(\n        v16,", setup)
        self.assertIn("ensure_scoped_ui(\n        v17,", setup)
        self.assertIn('scoped_factories=("select",)', setup)

    def test_operational_scroll_uses_static_module_local_override(self) -> None:
        source = self._source("operational_planning_compat.py")
        self.assertIn('static_overrides={"scroll_area": _horizontal_container}', source)
        self.assertIn('OPERATIONAL_SCROLL_CLASS = "v18-operational-scroll"', source)
        self.assertIn(".schedule-grid", source)
        self.assertNotIn("original_scroll_area", source)
        self.assertNotIn("PlannerUI.render_planning =", source)

    def test_segment_parent_navigation_reuses_scoped_facade(self) -> None:
        source = self._source("segment_navigation_compat.py")
        self.assertIn("ensure_scoped_ui(", source)
        self.assertIn('with scoped_ui.override_factory("select", select_with_parent_link):', source)
        self.assertNotIn("ContextVar", source)
        self.assertNotIn("ui.select =", source)

    def test_resource_class_precedence_is_an_explicit_compatibility_rule(self) -> None:
        source = self._source("resource_class_compat.py")
        self.assertIn('if "installation" in text or "installateur" in text:', source)
        self.assertIn('return "Installation"', source)
        self.assertIn("original_normalize(value)", source)


if __name__ == "__main__":
    unittest.main()
