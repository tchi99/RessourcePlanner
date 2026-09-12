from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReactProjectsContractTests(unittest.TestCase):
    def test_shell_routes_projects_to_real_page(self) -> None:
        app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
        main = (ROOT / "frontend" / "src" / "main.tsx").read_text(encoding="utf-8")

        self.assertIn('import ProjectsPage from "./ProjectsPage"', app)
        self.assertIn('view === "projects"', app)
        self.assertIn("<ProjectsPage />", app)
        self.assertIn('import "./projects.css"', main)

    def test_projects_page_reads_sql_and_integration_status_through_fastapi(self) -> None:
        page = (ROOT / "frontend" / "src" / "ProjectsPage.tsx").read_text(
            encoding="utf-8"
        )
        api = (ROOT / "frontend" / "src" / "api.ts").read_text(encoding="utf-8")

        self.assertIn("getProjects(false, controller.signal)", page)
        self.assertIn("getAcumaticaIntegrationStatus(controller.signal)", page)
        self.assertIn("await syncAcumaticaProjects()", page)
        self.assertIn("const projectRows = await getProjects(false)", page)
        self.assertIn('"/api/v1/integrations/acumatica"', api)
        self.assertIn('"/api/v1/integrations/acumatica/projects/sync"', api)
        self.assertNotIn("/entity/", page)
        self.assertNotIn("ACUMATICA_ACCESS_TOKEN", page)

    def test_projects_page_uses_backend_active_state_and_expected_filters(self) -> None:
        page = (ROOT / "frontend" / "src" / "ProjectsPage.tsx").read_text(
            encoding="utf-8"
        )
        api = (ROOT / "frontend" / "src" / "api.ts").read_text(encoding="utf-8")

        self.assertIn("active: boolean", api)
        self.assertIn("project.active", page)
        self.assertIn("État calculé par le backend", page)
        self.assertIn("Chargé de projet", page)
        self.assertIn("Source", page)
        self.assertIn("Acumatica", page)
        self.assertIn("Local", page)
        self.assertIn("Liés ERP", page)
        self.assertNotIn('includes("terminé")', page)
        self.assertNotIn('includes("fermé")', page)
        self.assertNotIn('includes("annulé")', page)

    def test_manual_sync_is_only_rendered_when_backend_reports_configured(self) -> None:
        page = (ROOT / "frontend" / "src" / "ProjectsPage.tsx").read_text(
            encoding="utf-8"
        )

        self.assertIn("integration?.configured && (", page)
        self.assertIn("Synchroniser les projets", page)
        self.assertIn("Non configurée sur ce serveur", page)
        self.assertIn("Le portefeuille local SQL demeure entièrement utilisable", page)


if __name__ == "__main__":
    unittest.main()
