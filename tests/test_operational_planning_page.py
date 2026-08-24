from __future__ import annotations

from pathlib import Path
import unittest

import app.operational_planning_page as planning_page
from app.operational_planning_page import OperationalPlanningPage


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


class OperationalPlanningPageTests(unittest.TestCase):
    def tearDown(self) -> None:
        planning_page._registered_renderer = None

    def test_page_invokes_injected_renderer_with_owner(self) -> None:
        owner = object()
        calls: list[object] = []
        page = OperationalPlanningPage(owner, calls.append)

        page.render()

        self.assertEqual(calls, [owner])

    def test_registry_accepts_callable_and_rejects_invalid_renderer(self) -> None:
        renderer = lambda owner: None
        planning_page.register_operational_planning_renderer(renderer)
        self.assertIs(planning_page._registered_renderer, renderer)
        with self.assertRaises(TypeError):
            planning_page.register_operational_planning_renderer(None)  # type: ignore[arg-type]

    def test_base_ui_routes_planning_through_explicit_page(self) -> None:
        source = (APP / "ui.py").read_text(encoding="utf-8")
        self.assertIn("from .operational_planning_page import OperationalPlanningPage", source)
        self.assertIn("self.operational_planning_page = OperationalPlanningPage(", source)
        self.assertIn("self.operational_planning_page.render()", source)
        self.assertNotIn('elif self.current_page == "planning":\n            self.render_planning()', source)

    def test_final_v17_sort_layer_registers_renderer_without_legacy_alias_rewrites(self) -> None:
        source = (APP / "v17_sort_fix.py").read_text(encoding="utf-8")
        self.assertIn(
            "from .operational_planning_page import register_operational_planning_renderer",
            source,
        )
        self.assertIn("register_operational_planning_renderer(render_planning)", source)
        for token in (
            "PlannerUI.render_planning = render_planning",
            "v13._render_operational_planning = render_planning",
            "v15._render_operational_planning_v15 = render_planning",
            "v15_refinements._render_planning = render_planning",
            "v16._render_planning_v16 = render_planning",
            "v16_refinements._render_planning = render_planning",
            "v17_refinements._render_planning = render_planning",
        ):
            self.assertNotIn(token, source)

    def test_installer_prefers_registered_renderer_without_importing_versioned_modules(self) -> None:
        source = (APP / "operational_planning_page.py").read_text(encoding="utf-8")
        self.assertIn("renderer = _registered_renderer", source)
        self.assertIn("PlannerUI._operational_planning_renderer = renderer", source)
        for token in ("import v13", "import v15", "import v16", "import v17", "import v18"):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
