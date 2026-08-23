from __future__ import annotations

from pathlib import Path
import unittest

from app.operational_planning_page import OperationalPlanningPage


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


class OperationalPlanningPageTests(unittest.TestCase):
    def test_page_invokes_injected_renderer_with_owner(self) -> None:
        owner = object()
        calls: list[object] = []
        page = OperationalPlanningPage(owner, calls.append)

        page.render()

        self.assertEqual(calls, [owner])

    def test_base_ui_routes_planning_through_explicit_page(self) -> None:
        source = (APP / "ui.py").read_text(encoding="utf-8")
        self.assertIn("from .operational_planning_page import OperationalPlanningPage", source)
        self.assertIn("self.operational_planning_page = OperationalPlanningPage(", source)
        self.assertIn("self.operational_planning_page.render()", source)
        self.assertNotIn('elif self.current_page == "planning":\n            self.render_planning()', source)

    def test_installer_captures_final_renderer_without_importing_versioned_modules(self) -> None:
        source = (APP / "operational_planning_page.py").read_text(encoding="utf-8")
        self.assertIn('getattr(ui_module.PlannerUI, "render_planning", None)', source)
        self.assertIn("PlannerUI._operational_planning_renderer = renderer", source)
        for token in ("import v13", "import v15", "import v16", "import v17", "import v18"):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
