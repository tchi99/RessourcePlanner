from pathlib import Path
import unittest


class FrontendPipelineContractTests(unittest.TestCase):
    def test_dashboard_renders_extended_pipeline_horizons_and_gate_types(self):
        cockpit_root = Path(__file__).resolve().parents[2]
        app = (cockpit_root / "frontend" / "src" / "App.tsx").read_text(
            encoding="utf-8"
        )
        types = (cockpit_root / "frontend" / "src" / "types.ts").read_text(
            encoding="utf-8"
        )

        for label in ("Maintenant", "Ensuite", "Plus tard"):
            self.assertIn(label, app)
        self.assertIn("data.pipeline.now", app)
        self.assertIn("data.pipeline.next", app)
        self.assertIn("data.pipeline.later", app)
        self.assertIn("ARCHITECTURE_GATE", app)
        self.assertIn("ENVIRONMENT_GATE", app)
        self.assertIn("slice(0, 6)", app)

        self.assertIn("'WORK'", types)
        self.assertIn("'ARCHITECTURE_GATE'", types)
        self.assertIn("'ENVIRONMENT_GATE'", types)
        self.assertIn("pipeline:", types)


if __name__ == "__main__":
    unittest.main()
