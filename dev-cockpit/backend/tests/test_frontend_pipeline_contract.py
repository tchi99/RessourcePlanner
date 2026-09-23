from pathlib import Path
import unittest


class FrontendPipelineContractTests(unittest.TestCase):
    def test_product_owner_owns_extended_pipeline_and_main_dashboard_does_not(self):
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

        self.assertNotIn("TRAJECTOIRE PRODUIT", app)
        self.assertNotIn("data.pipeline.now", app)

        self.assertIn("Trajectoire produit", panel)
        for label in ("Maintenant", "Ensuite", "Plus tard"):
            self.assertIn(label, panel)
        self.assertIn("dashboard.pipeline.now", panel)
        self.assertIn("dashboard.pipeline.next", panel)
        self.assertIn("dashboard.pipeline.later", panel)
        self.assertIn("PipelineHorizonGroup", panel)
        self.assertIn("PipelineStepAccordion", panel)
        self.assertIn("/api/details/issues/", panel)
        self.assertIn("exactSection", panel)

        self.assertIn("'WORK'", types)
        self.assertIn("'ARCHITECTURE_GATE'", types)
        self.assertIn("'ENVIRONMENT_GATE'", types)
        self.assertIn("status: string | null", types)
        self.assertIn("rationale: string | null", types)


if __name__ == "__main__":
    unittest.main()
