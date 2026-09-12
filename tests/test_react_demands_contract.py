from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReactDemandsContractTests(unittest.TestCase):
    def test_shell_routes_demands_view_to_real_workspace(self) -> None:
        app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
        workspace = (ROOT / "frontend" / "src" / "DemandsWorkspace.tsx").read_text(
            encoding="utf-8"
        )
        main = (ROOT / "frontend" / "src" / "main.tsx").read_text(encoding="utf-8")

        self.assertIn('import DemandsWorkspace from "./DemandsWorkspace"', app)
        self.assertIn('view === "demands"', app)
        self.assertIn("<DemandsWorkspace />", app)
        self.assertIn("<DemandsPage />", workspace)
        self.assertIn('import "./demands.css"', main)

    def test_api_client_uses_canonical_demand_and_work_package_endpoints(self) -> None:
        source = (ROOT / "frontend" / "src" / "api.ts").read_text(encoding="utf-8")

        self.assertIn('"/api/v1/demands"', source)
        self.assertIn('/api/v1/demands/${encodeURIComponent(number)}', source)
        self.assertIn("/api/v1/work-packages?", source)
        self.assertIn('"Idempotency-Key"', source)
        self.assertIn("work_package_ref", source)

    def test_creation_reuses_idempotency_key_for_identical_retry(self) -> None:
        source = (ROOT / "frontend" / "src" / "DemandsPage.tsx").read_text(
            encoding="utf-8"
        )

        self.assertIn("previous?.fingerprint === fingerprint", source)
        self.assertIn("createRetry.current = { fingerprint, key }", source)
        self.assertIn("await createDemand(payload, key)", source)
        self.assertIn("if (saving) return", source)

    def test_editor_preserves_business_separation_and_authoritative_references(self) -> None:
        source = (ROOT / "frontend" / "src" / "DemandsPage.tsx").read_text(
            encoding="utf-8"
        )

        self.assertIn("Responsable projet", source)
        self.assertIn("restent en lecture seule", source)
        self.assertIn("Plage moyen terme / WorkPackage", source)
        self.assertIn('value="Tentative"', source)
        self.assertIn('value="Confirmée"', source)
        self.assertIn("Approbation ≠ confirmation", source)
        self.assertNotIn('name="project_manager"', source)


if __name__ == "__main__":
    unittest.main()
