from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReactCoordinatorDashboardContractTests(unittest.TestCase):
    def test_dashboard_uses_dedicated_backend_read_model(self) -> None:
        api = (ROOT / "frontend" / "src" / "api.ts").read_text(encoding="utf-8")
        page = (ROOT / "frontend" / "src" / "CoordinatorDashboardPage.tsx").read_text(
            encoding="utf-8"
        )
        routes = (ROOT / "app" / "server" / "routes_reads.py").read_text(
            encoding="utf-8"
        )

        self.assertIn('"/api/v1/coordinator-dashboard"', api)
        self.assertIn("CoordinatorDashboardReadModel", api)
        self.assertIn("getCoordinatorDashboard", page)
        self.assertIn('@router.get("/coordinator-dashboard")', routes)
        self.assertIn("CoordinatorDashboardService", routes)

    def test_react_consumes_projected_attention_and_action_categories(self) -> None:
        page = (ROOT / "frontend" / "src" / "CoordinatorDashboardPage.tsx").read_text(
            encoding="utf-8"
        )

        self.assertIn("action.category", page)
        self.assertIn("action.attention", page)
        self.assertIn("action.target", page)
        self.assertIn("dashboard.personal_demands", page)
        self.assertNotIn("demand_cancellation_policy", page)
        self.assertNotIn("actor_approvable_requirement_ids", page)
        self.assertNotIn("automatic_rebuild_hours", page)

    def test_coordinator_navigation_links_to_canonical_demands_and_planning(self) -> None:
        app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
        workspace = (ROOT / "frontend" / "src" / "DemandsWorkspace.tsx").read_text(
            encoding="utf-8"
        )

        self.assertIn('role: "COORDINATOR"', app)
        self.assertIn("<CoordinatorDashboardPage", app)
        self.assertIn('setView("planning")', app)
        self.assertIn('setView("demands")', app)
        self.assertIn("initialDemandNumber", workspace)


if __name__ == "__main__":
    unittest.main()
