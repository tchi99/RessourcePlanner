from __future__ import annotations

from pathlib import Path
import unittest

from app.runtime_composition import RUNTIME_COMPOSITION_MANIFEST, composition_manifest


class RuntimeCompositionTests(unittest.TestCase):
    def test_manifest_is_explicit_unique_and_stable_at_boundaries(self) -> None:
        manifest = composition_manifest()
        names = [step.name for step in manifest]

        self.assertEqual(manifest, RUNTIME_COMPOSITION_MANIFEST)
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(names[0], "nicegui_compat")
        self.assertEqual(names[-1], "thunderbird_setup")
        self.assertLess(names.index("runtime_optimizations"), names.index("features"))
        self.assertLess(names.index("v18_workflow_fixes"), names.index("communication_ui"))

    def test_manifest_makes_transitional_legacy_steps_visible(self) -> None:
        legacy = [step.name for step in composition_manifest() if step.category == "legacy"]
        communications = [
            step.name for step in composition_manifest() if step.category == "communications"
        ]

        # These assertions intentionally inventory technical debt. Future #15 tranches
        # should make this list smaller as explicit services/pages replace installers.
        self.assertIn("v13_features", legacy)
        self.assertIn("v18_workflow_fixes", legacy)
        self.assertEqual(
            communications,
            [
                "communication_ui",
                "communication_obsolescence",
                "communication_outlook",
                "communication_mail_clients",
                "thunderbird_setup",
            ],
        )

    def test_main_is_only_a_composition_root_consumer(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")

        self.assertIn("install_runtime_features()", source)
        self.assertIn("install_planning_engine(config.planning_engine_mode)", source)
        for historical_prefix in (
            "install_v13_",
            "install_v14_",
            "install_v15_",
            "install_v16_",
            "install_v17_",
            "install_v18_",
        ):
            self.assertNotIn(historical_prefix, source)


if __name__ == "__main__":
    unittest.main()
