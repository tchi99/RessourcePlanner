from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BootstrapProjectTaskContractTests(unittest.TestCase):
    def test_configuration_exposes_canonical_acumatica_project_sync(self) -> None:
        page = (ROOT / "frontend" / "src" / "ConfigurationPage.tsx").read_text(encoding="utf-8")
        panel = (ROOT / "frontend" / "src" / "AcumaticaProjectSyncPanel.tsx").read_text(encoding="utf-8")
        api = (ROOT / "frontend" / "src" / "acumaticaIntegrationApi.ts").read_text(encoding="utf-8")

        self.assertIn("<AcumaticaProjectSyncPanel />", page)
        self.assertIn("Synchroniser les projets", panel)
        for label in ("Reçus", "Créés", "Mis à jour", "Inchangés", "Erreurs"):
            self.assertIn(label, panel)
        self.assertIn("/api/v1/integrations/acumatica/projects/sync", api)
        self.assertNotIn("import-projects", panel)

    def test_task_bootstrap_documentation_states_minimal_contract_and_replay(self) -> None:
        doc = (ROOT / "docs" / "ERP_TASK_CATALOG.md").read_text(encoding="utf-8")

        for required in ("ID projet", "ID tâche", "Description", "Statut"):
            self.assertIn(required, doc)
        self.assertIn("Sans changement", doc)
        self.assertIn("erp_task_catalog_duplicate_key", doc)
        self.assertIn("erp_task_catalog_row_invalid", doc)
        self.assertIn("--apply", doc)


if __name__ == "__main__":
    unittest.main()
