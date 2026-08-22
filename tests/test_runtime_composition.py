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
        self.assertLess(names.index("v18_features"), names.index("effort_identity_guard"))
        self.assertLess(names.index("effort_identity_guard"), names.index("v18_refinements"))
        self.assertLess(names.index("v18_refinements"), names.index("operational_planning_compat"))
        self.assertLess(names.index("operational_planning_compat"), names.index("resource_class_compat"))
        self.assertLess(names.index("resource_class_compat"), names.index("segment_navigation_compat"))
        self.assertLess(names.index("segment_navigation_compat"), names.index("location_projection"))
        self.assertLess(names.index("location_projection"), names.index("planning_service_ui"))
        self.assertLess(names.index("planning_service_ui"), names.index("demand_service_ui"))
        self.assertLess(names.index("demand_service_ui"), names.index("allocation_service_ui"))
        self.assertLess(names.index("allocation_service_ui"), names.index("pure_validation_ui"))
        self.assertLess(names.index("pure_validation_ui"), names.index("communication_ui"))

    def test_manifest_makes_transitional_legacy_steps_visible(self) -> None:
        legacy = [step.name for step in composition_manifest() if step.category == "legacy"]
        application = [step.name for step in composition_manifest() if step.category == "application"]
        compatibility = [step.name for step in composition_manifest() if step.category == "compatibility"]
        communications = [step.name for step in composition_manifest() if step.category == "communications"]

        self.assertIn("v13_features", legacy)
        for retired in (
            "v18_fixes",
            "v18_single_scroll",
            "v18_calendar_sizing",
            "v18_workflow_fixes",
        ):
            self.assertNotIn(retired, legacy)
        for extracted in (
            "effort_identity_guard",
            "operational_planning_compat",
            "resource_class_compat",
            "segment_navigation_compat",
            "location_projection",
        ):
            self.assertIn(extracted, compatibility)
        self.assertNotIn("demand_legacy_cleanup", compatibility)
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

    def test_retired_compatibility_modules_are_physically_removed(self) -> None:
        app_dir = Path(__file__).resolve().parents[1] / "app"
        for name in (
            "v18_fixes.py",
            "v18_single_scroll.py",
            "v18_calendar_sizing.py",
            "v18_workflow_fixes.py",
            "demand_legacy_cleanup.py",
        ):
            self.assertFalse((app_dir / name).exists(), name)

    def test_main_is_only_a_composition_root_consumer(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")

        self.assertIn("install_runtime_features()", source)
        self.assertIn("install_planning_engine()", source)
        self.assertNotIn("planning_engine_mode", source)
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
        source = (Path(__file__).resolve().parents[1] / "app" / "planning_service_ui.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("planning_service(self.repo).rebuild()", source)
        self.assertIn("v15_refinements._recalculate = _recalculate_via_service", source)
        self.assertNotIn("rebuild_allocations_refined(self.repo)", source)

    def test_allocation_service_binding_owns_operational_mutation_entry_points(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "app" / "allocation_service_ui.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("AllocationService(", source)
        self.assertIn("v15_engine.create_manual_allocation = _create_manual_via_service", source)
        self.assertIn("v15_engine.update_manual_allocation = _update_manual_via_service", source)
        self.assertIn("v15_engine.release_manual_allocation = _release_manual_via_service", source)
        self.assertIn("v15_engine.delete_manual_allocation = _delete_manual_via_service", source)
        self.assertIn("v16._assign_segment = _assign_segment_via_service", source)

    def test_pure_validation_binding_records_authoritative_engine_cycles(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "app" / "pure_validation_ui.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("record_pure_cycle(data)", source)
        self.assertIn(
            "planning_cutover._publish_planning_performance = publish_with_validation",
            source,
        )
        self.assertIn("moteur autoritaire unique", source)
        self.assertNotIn("guarded_pure", source)
        self.assertNotIn("save_planning_engine_mode", source)


if __name__ == "__main__":
    unittest.main()
