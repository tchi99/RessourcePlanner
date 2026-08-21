from __future__ import annotations

from pathlib import Path
import unittest


class NiceGUIGlobalMutationTests(unittest.TestCase):
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
        self.assertEqual(
            offenders,
            [],
            "The operational renderer must use its module-local adapter instead of "
            "replacing NiceGUI's global scroll_area factory.",
        )

    def test_remaining_select_factory_mutations_are_explicit_debt(self) -> None:
        offenders = sorted(
            set(self._offenders("ui.select =") + self._offenders("nicegui_ui.select ="))
        )
        self.assertEqual(
            offenders,
            [
                "v16_refinements.py",
                "v17_refinements.py",
                "v18_workflow_fixes.py",
            ],
            "Keep the known select-wrapper debt explicit. Future #15 tranches should "
            "shrink this list; adding another global select mutation must fail CI.",
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
