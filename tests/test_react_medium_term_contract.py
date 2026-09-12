from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReactMediumTermContractTests(unittest.TestCase):
    def test_shell_routes_medium_term_to_real_page(self) -> None:
        app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
        main = (ROOT / "frontend" / "src" / "main.tsx").read_text(encoding="utf-8")

        self.assertIn('import MediumTermPage from "./MediumTermPage"', app)
        self.assertIn('view === "medium-term"', app)
        self.assertIn('<MediumTermPage onOpenDemands={() => setView("demands")} />', app)
        self.assertIn('import "./medium-term.css"', main)

    def test_page_uses_existing_canonical_read_endpoints(self) -> None:
        source = (ROOT / "frontend" / "src" / "MediumTermPage.tsx").read_text(
            encoding="utf-8"
        )

        self.assertIn("getProjects(true, controller.signal)", source)
        self.assertIn('getWorkPackages("", true, controller.signal)', source)
        self.assertIn("getPlanningSnapshot(start, end, controller.signal)", source)
        self.assertIn("snapshot.pending_loads", source)
        self.assertIn("snapshot.segments", source)
        self.assertNotIn("projected_hours_without_double_counting", source)
        self.assertNotIn("projected_period_hours", source)

    def test_page_exposes_work_packages_filters_backend_statuses_and_editor(self) -> None:
        source = (ROOT / "frontend" / "src" / "MediumTermPage.tsx").read_text(
            encoding="utf-8"
        )

        self.assertIn("Planification moyen terme", source)
        self.assertIn("Chargé de projet", source)
        self.assertIn("Horizon", source)
        self.assertIn("WorkPackages", source)
        self.assertIn("Modification en attente", source)
        self.assertIn("Charge potentielle", source)
        self.assertIn("Plan approuvé", source)
        self.assertIn("Ouvrir les demandes", source)
        self.assertIn("+ WorkPackage", source)
        self.assertIn("<WorkPackageEditor", source)
        self.assertIn("onEdit={setEditor}", source)
        self.assertIn("setRefreshKey((value) => value + 1)", source)
        self.assertIn("Les agrégations de capacité moyen terme seront ajoutées en 4C", source)

    def test_editor_uses_backend_mutations_and_reuses_creation_idempotency_key(self) -> None:
        editor = (ROOT / "frontend" / "src" / "WorkPackageEditor.tsx").read_text(
            encoding="utf-8"
        )
        api = (ROOT / "frontend" / "src" / "api.ts").read_text(encoding="utf-8")

        self.assertIn("await createWorkPackage(payload, key)", editor)
        self.assertIn("await updateWorkPackage(workPackage.reference, payload)", editor)
        self.assertIn("previous?.fingerprint === fingerprint", editor)
        self.assertIn("createRetry.current = { fingerprint, key }", editor)
        self.assertIn("if (saving) return", editor)
        self.assertIn("aucune demande n’est déjà liée", editor)
        self.assertIn('"/api/v1/work-packages"', api)
        self.assertIn('/api/v1/work-packages/${encodeURIComponent(reference)}', api)
        self.assertIn('"Idempotency-Key"', api)


if __name__ == "__main__":
    unittest.main()
