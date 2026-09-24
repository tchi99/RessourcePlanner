from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReactDemandWorkflowContractTests(unittest.TestCase):
    def test_workflow_is_contextual_inside_unified_demand_detail(self) -> None:
        workspace = (ROOT / "frontend" / "src" / "DemandsWorkspace.tsx").read_text(
            encoding="utf-8"
        )
        detail = (ROOT / "frontend" / "src" / "DemandDetail.tsx").read_text(
            encoding="utf-8"
        )
        main = (ROOT / "frontend" / "src" / "main.tsx").read_text(encoding="utf-8")

        self.assertIn("<DemandsPage />", workspace)
        self.assertNotIn("<DemandWorkflowPage />", workspace)
        self.assertIn("<DemandWorkflowPage", detail)
        self.assertIn("embedded", detail)
        self.assertIn('import "./demand-workflow.css"', main)

    def test_workflow_client_uses_authoritative_backend_policy(self) -> None:
        source = (ROOT / "frontend" / "src" / "demandWorkflowApi.ts").read_text(
            encoding="utf-8"
        )
        page = (ROOT / "frontend" / "src" / "DemandWorkflowPage.tsx").read_text(
            encoding="utf-8"
        )

        self.assertIn("/workflow-actions", source)
        self.assertIn("getDemandWorkflowState", source)
        self.assertIn("expected_version", source)
        self.assertIn("/api/v1/demands/${encodeURIComponent(number)}/${action}", source)
        self.assertIn("workflowState?.available_actions", page)
        self.assertIn("getDemandDetail", page)
        self.assertIn("canonicalDetail.workflow as DemandWorkflowState", page)
        self.assertNotIn("getDemandWorkflowState", page)
        self.assertIn("workflowState?.version ?? selectedDemand.version", page)
        self.assertNotIn("function expectedActions", page)

    def test_workflow_separates_approval_from_confirmation(self) -> None:
        source = (ROOT / "frontend" / "src" / "DemandWorkflowPage.tsx").read_text(
            encoding="utf-8"
        )

        self.assertIn("Approbation / statut", source)
        self.assertIn("Confirmation", source)
        self.assertIn("Approbation ≠ confirmation.", source)
        self.assertIn("selectedDemand.confirmation", source)
        self.assertIn("selectedDemand.status", source)

    def test_workflow_blocks_mutations_while_any_editor_is_dirty(self) -> None:
        detail = (ROOT / "frontend" / "src" / "DemandDetail.tsx").read_text(
            encoding="utf-8"
        )
        page = (ROOT / "frontend" / "src" / "DemandWorkflowPage.tsx").read_text(
            encoding="utf-8"
        )
        demands = (ROOT / "frontend" / "src" / "DemandsPage.tsx").read_text(
            encoding="utf-8"
        )

        self.assertIn("hasUnsavedChanges={editorDirty || contextDirty}", demands)
        self.assertIn("hasUnsavedChanges={hasUnsavedChanges}", detail)
        self.assertIn("if (hasUnsavedChanges)", page)
        self.assertIn("Enregistre les modifications avant de poursuivre.", page)
        self.assertIn("disabled={busy || hasUnsavedChanges}", page)

    def test_workflow_requires_correction_comment_and_guards_double_clicks(self) -> None:
        source = (ROOT / "frontend" / "src" / "DemandWorkflowPage.tsx").read_text(
            encoding="utf-8"
        )

        self.assertIn("if (!selectedDemand || pendingAction) return", source)
        self.assertIn('action === "correction" && !correctionComment.trim()', source)
        self.assertIn("disabled={busy || !correctionComment.trim()}", source)
        self.assertIn("const busy = pendingAction !== null", source)
        self.assertIn("await refresh(result.demand_number)", source)
        self.assertIn("result.planning", source)


if __name__ == "__main__":
    unittest.main()
