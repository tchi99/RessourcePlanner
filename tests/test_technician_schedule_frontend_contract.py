from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TechnicianScheduleFrontendContractTests(unittest.TestCase):
    def test_frontend_uses_personal_schedule_endpoint_without_resource_selector(self) -> None:
        api = (ROOT / "frontend" / "src" / "technicianScheduleApi.ts").read_text(encoding="utf-8")
        self.assertIn("/api/v1/me/schedule", api)
        self.assertIn("new URLSearchParams({ start, end })", api)
        self.assertNotIn("resource_id", api)
        self.assertNotIn("resource_name", api)

    def test_page_exposes_three_personal_schedule_views(self) -> None:
        page = (ROOT / "frontend" / "src" / "TechnicianSchedulePage.tsx").read_text(encoding="utf-8")
        self.assertIn("Aujourd’hui", page)
        self.assertIn("Demain", page)
        self.assertIn("Ma semaine", page)
        self.assertIn('schedule?.link_status === "UNLINKED"', page)
        self.assertIn('schedule?.link_status === "RESOURCE_NOT_FOUND"', page)
        self.assertIn('schedule?.link_status === "LINKED"', page)

    def test_technician_only_account_defaults_to_my_schedule(self) -> None:
        app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
        self.assertIn('key: "my-schedule"', app)
        self.assertIn('principal.roles.length === 1 && principal.roles.includes("TECHNICIAN")', app)
        self.assertIn("<TechnicianSchedulePage />", app)


if __name__ == "__main__":
    unittest.main()
