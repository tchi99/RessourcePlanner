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
        self.assertLess(names.index("v18_workflow_fixes"), names.index("location_projection"))
        self.assertLess(names.index("location_projection"), names.index("demand_legacy_cleanup"))
        self.assertLess(names.index("v18_workflow_fixes"), names.index("planning_service_ui"))
        self.assertLess(names.index("planning_service_ui"), names.index("demand_service_ui"))
        self.assertLess(names.index("demand_service_ui"), names.index("allocation_service_ui"))
        self.assertLess(names.index("allocation_service_ui"), names.index("pure_validation_ui"))
        self.assertLess(names.index("pure_validation_ui"), names.index("communication_ui"))

    def test_manifest_makes_transitional_legacy_steps_visible(self) -> None:
        legacy = [step.name for step in composition_manifest() if step.category == "legacy"]
        application = [
            step.name for step in composition_manifest() if step.category == "application"
        ]
        compatibility = [
            step.name for step in composition_manifest() if step.category == "compatibility"
        ]
        communications = [
            step.name for step in composition_manifest() if step.category == "communications"
        ]

        # These assertions intentionally inventory technical debt. Future #15 tranches
        # should make this list smaller as explicit services/pages replace installers.
        self.assertIn("v13_features", legacy)
        self.assertIn("v18_workflow_fixes", legacy)
        self.assertIn("location_projection", compatibility)
        self.assertEqual(
            application,
            [
                "planning_service_ui",
                "demand_service_ui",
                "allocation_service_ui",
                "pure_validation_ui",
            ],
        )
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

    def test_planning_service_ui_binding_routes_recalculate_through_service(self) -> None:
        source = (
            Path(__file__).resolve().parents[1] / "app" / "planning_service_ui.py"
        ).read_text(encoding="utf-8")

        self.assertIn("planning_service(self.repo).rebuild()", source)
        self.assertIn("v15_refinements._recalculate = _recalculate_via_service", source)
        self.assertNotIn("rebuild_allocations_refined(self.repo)", source)

    def test_allocation_service_binding_owns_operational_mutation_entry_points(self) -> None:
        source = (
            Path(__file__).resolve().parents[1] / "app" / "allocation_service_ui.py"
        ).read_text(encoding="utf-8")

        self.assertIn("AllocationService(", source)
        self.assertIn("v15_engine.create_manual_allocation = _create_manual_via_service", source)
        self.assertIn("v15_engine.update_manual_allocation = _update_manual_via_service", source)
        self.assertIn("v15_engine.release_manual_allocation = _release_manual_via_service", source)
        self.assertIn("v15_engine.delete_manual_allocation = _delete_manual_via_service", source)
        self.assertIn("v16._assign_segment = _assign_segment_via_service", source)

    def test_pure_validation_binding_records_authoritative_engine_cycles(self) -> None:
        source = (
            Path(__file__).resolve().parents[1] / "app" / "pure_validation_ui.py"
        ).read_text(encoding="utf-8")

        self.assertIn("record_pure_cycle(data)", source)
        self.assertIn(
            "planning_cutover._publish_planning_performance = publish_with_validation",
            source,
        )
        self.assertIn("save_planning_engine_mode(mode)", source)
        self.assertIn("Activer le moteur pur au prochain redémarrage", source)


if __name__ == "__main__":
    unittest.main()
