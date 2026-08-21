from __future__ import annotations

from pathlib import Path
import unittest


class NiceGUIGlobalMutationTests(unittest.TestCase):
    def test_renderers_do_not_replace_global_component_factories(self) -> None:
        app_dir = Path(__file__).resolve().parents[1] / "app"
        forbidden = (
            "ui.scroll_area =",
            "nicegui_ui.scroll_area =",
            "ui.select =",
            "nicegui_ui.select =",
        )

        offenders: list[str] = []
        for path in sorted(app_dir.glob("*.py")):
            source = path.read_text(encoding="utf-8")
            for token in forbidden:
                if token in source:
                    offenders.append(f"{path.name}: {token}")

        self.assertEqual(
            offenders,
            [],
            "NiceGUI component factories must not be replaced globally at render time; "
            "use an explicit component or a module-local adapter instead.",
        )

    def test_single_scroll_adapter_no_longer_wraps_planner_render(self) -> None:
        path = Path(__file__).resolve().parents[1] / "app" / "v18_single_scroll.py"
        source = path.read_text(encoding="utf-8")

        self.assertIn("class _OperationalPlanningUI", source)
        self.assertIn("v17.ui = _OperationalPlanningUI(current_ui)", source)
        self.assertNotIn("original_scroll_area", source)
        self.assertNotIn("PlannerUI.render_planning =", source)


if __name__ == "__main__":
    unittest.main()
