from __future__ import annotations

from pathlib import Path
import unittest


class MediumTermCapacityArchitectureTests(unittest.TestCase):
    def test_projection_policy_is_ui_and_storage_neutral(self) -> None:
        app_dir = Path(__file__).resolve().parents[1] / "app"
        source = (app_dir / "domain" / "capacity_projection.py").read_text(encoding="utf-8")
        for forbidden in ("nicegui", "xlwings", "sqlalchemy", "ExcelRepository", "v18"):
            self.assertNotIn(forbidden, source)

    def test_projection_renderer_is_registered_through_existing_page_boundary(self) -> None:
        app_dir = Path(__file__).resolve().parents[1] / "app"
        renderer = (app_dir / "medium_term_renderer_compat.py").read_text(encoding="utf-8")
        page = (app_dir / "medium_term_page.py").read_text(encoding="utf-8")
        self.assertIn("register_medium_term_renderer", renderer)
        self.assertIn("MediumTermPage", page)
        self.assertNotIn("PlannerUI._render_medium_term", renderer)


if __name__ == "__main__":
    unittest.main()
