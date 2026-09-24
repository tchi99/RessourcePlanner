from pathlib import Path
import unittest


class FrontendPipelineContractTests(unittest.TestCase):
    def test_dashboard_shows_canonical_horizons_and_po_keeps_extended_pipeline(self):
        cockpit_root = Path(__file__).resolve().parents[2]
        app = (cockpit_root / "frontend" / "src" / "App.tsx").read_text(
            encoding="utf-8"
        )
        panel = (cockpit_root / "frontend" / "src" / "RoleDetailPanel.tsx").read_text(
            encoding="utf-8"
        )
        types = (cockpit_root / "frontend" / "src" / "types.ts").read_text(
            encoding="utf-8"
        )

        self.assertIn("data.pipeline.now", app)
        self.assertIn("data.pipeline.parallel", app)
        self.assertIn("data.pipeline.valid", app)
        self.assertIn("Pipeline #55 invalide", app)
        self.assertIn("COHÉRENCE ROADMAP", app)
        self.assertIn("Préparer la mise à jour de #55", app)
        self.assertIn("data.reconciliation", app)
        self.assertIn("PARALLÈLE DISPONIBLE", app)
        self.assertIn("ENSUITE", app)

        self.assertIn("Trajectoire produit", panel)
        for label in ("Maintenant", "En parallèle", "Ensuite", "Plus tard"):
            self.assertIn(label, panel)
        self.assertIn("dashboard.pipeline.now", panel)
        self.assertIn("dashboard.pipeline.parallel", panel)
        self.assertIn("dashboard.pipeline.next", panel)
        self.assertIn("dashboard.pipeline.later", panel)
        self.assertIn("PipelineHorizonGroup", panel)
        self.assertIn("PipelineStepAccordion", panel)
        self.assertIn("PipelineUnavailable", panel)
        self.assertIn("/api/details/issues/", panel)
        self.assertIn("exactSection", panel)

        self.assertIn("'WORK'", types)
        self.assertIn("'ARCHITECTURE_GATE'", types)
        self.assertIn("'ENVIRONMENT_GATE'", types)
        self.assertIn("status: string | null", types)
        self.assertIn("rationale: string | null", types)
        self.assertIn("lane: 'MAIN' | 'PARALLEL'", types)
        self.assertIn("parallel: PipelineStep[]", types)
        self.assertIn("valid: boolean", types)
        self.assertIn("source: 'canonical_v1' | 'legacy'", types)
        self.assertIn("errors: string[]", types)
        self.assertIn("active_issue: number | null", types)
        self.assertIn("PipelineReconciliation", types)
        self.assertIn("reconciliation: PipelineReconciliation", types)
        self.assertIn("'coherent' | 'stale' | 'attention' | 'invalid' | 'legacy'", types)
        self.assertIn("pipeline_block: string", types)


if __name__ == "__main__":
    unittest.main()
