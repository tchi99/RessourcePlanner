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
        self.assertIn("/detail", source)
        self.assertIn("DemandDetailReadModel", source)
        self.assertIn('"Idempotency-Key"', source)
        self.assertIn("work_package_ref", source)

    def test_list_composes_terminal_filter_status_project_search_and_creation_sort(self) -> None:
        source = (ROOT / "frontend" / "src" / "DemandsPage.tsx").read_text(
            encoding="utf-8"
        )
        api = (ROOT / "frontend" / "src" / "api.ts").read_text(encoding="utf-8")

        self.assertIn("effective_status?: string | null", api)
        self.assertIn("terminal?: boolean", api)
        self.assertIn("created_at?: string | null", api)
        self.assertIn("Inclure les demandes terminées", source)
        self.assertIn("Plus récentes d’abord", source)
        self.assertIn("Plus anciennes d’abord", source)
        self.assertIn('useState<"newest" | "oldest">("newest")', source)
        self.assertIn(
            'if (!includeTerminated && statusFilter === "all" && demand.terminal)',
            source,
        )
        self.assertIn(
            'if (statusFilter !== "all" && effectiveStatus !== statusFilter)',
            source,
        )
        self.assertIn(
            'if (projectFilter !== "all" && demand.project_number !== projectFilter)',
            source,
        )
        self.assertIn("demandSearchText(demand)", source)
        self.assertIn('sortOrder === "newest" ? -1 : 1', source)
        self.assertIn("demandCreatedAtMs(left) - demandCreatedAtMs(right)", source)
        self.assertIn(
            "[demands, search, statusFilter, projectFilter, includeTerminated, sortOrder]",
            source,
        )
        self.assertNotIn("desired_start) -", source)

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
        self.assertIn("getDemandDetail", source)
        self.assertIn("<DemandDetail", source)
        self.assertIn("canonicalDetail={selectedDetail}", source)
        self.assertIn("hasUnsavedChanges={editorDirty || contextDirty}", source)
        self.assertIn("confirmDiscardChanges", source)
        self.assertNotIn('name="project_manager"', source)


if __name__ == "__main__":
    unittest.main()
