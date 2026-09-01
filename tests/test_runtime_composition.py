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
        self.assertLess(names.index("v16_refinements"), names.index("operational_planning_runtime"))
        self.assertLess(names.index("operational_planning_runtime"), names.index("resource_management"))
        self.assertLess(names.index("resource_management"), names.index("operational_planning_sorting"))
        self.assertLess(names.index("operational_planning_sorting"), names.index("runtime_performance"))
        self.assertLess(names.index("runtime_performance"), names.index("resource_local_preferences"))
        self.assertLess(names.index("resource_local_preferences"), names.index("effort_identity"))
        self.assertLess(names.index("effort_identity"), names.index("effort_identity_guard"))
        self.assertLess(names.index("effort_identity_guard"), names.index("demand_cancellation"))
        self.assertLess(names.index("demand_cancellation"), names.index("medium_term_renderer"))
        self.assertLess(names.index("medium_term_renderer"), names.index("quick_shift_ui"))
        self.assertLess(names.index("quick_shift_ui"), names.index("operational_planning_compat"))
        self.assertLess(names.index("operational_planning_compat"), names.index("resource_class_compat"))
        self.assertLess(names.index("resource_class_compat"), names.index("location_projection"))
        self.assertLess(names.index("location_projection"), names.index("medium_term_page"))
        self.assertLess(names.index("medium_term_page"), names.index("operational_planning_page"))
        self.assertLess(names.index("operational_planning_page"), names.index("demand_editor_ui"))
        self.assertLess(names.index("demand_editor_ui"), names.index("planning_service_ui"))
        self.assertLess(names.index("planning_service_ui"), names.index("allocation_service_ui"))
        self.assertLess(names.index("allocation_service_ui"), names.index("pure_validation_ui"))
        self.assertLess(names.index("pure_validation_ui"), names.index("communication_ui"))

    def test_manifest_makes_transitional_legacy_steps_visible(self) -> None:
        legacy = [step.name for step in composition_manifest() if step.category == "legacy"]
        application = [step.name for step in composition_manifest() if step.category == "application"]
        compatibility = [step.name for step in composition_manifest() if step.category == "compatibility"]
        communications = [step.name for step in composition_manifest() if step.category == "communications"]
        names = [step.name for step in composition_manifest()]

        self.assertIn("v13_features", legacy)
        for retired in (
            "v14_runtime",
            "v17_features",
            "v17_refinements",
            "v171_performance",
            "v171_local_preferences",
            "v18_features",
            "v18_refinements",
            "v18_fixes",
            "v18_single_scroll",
            "v18_calendar_sizing",
            "v18_workflow_fixes",
        ):
            self.assertNotIn(retired, legacy)
            self.assertNotIn(retired, names)
        for extracted in (
            "operational_planning_runtime",
            "resource_management",
            "operational_planning_sorting",
            "runtime_performance",
            "resource_local_preferences",
            "effort_identity",
            "effort_identity_guard",
            "demand_cancellation",
            "medium_term_renderer",
            "operational_planning_compat",
            "resource_class_compat",
            "location_projection",
        ):
            self.assertIn(extracted, compatibility)
        self.assertNotIn("quick_shift_ui", compatibility)
        self.assertNotIn("demand_legacy_cleanup", compatibility)
        self.assertEqual(
            application,
            [
                "quick_shift_ui",
                "medium_term_page",
                "operational_planning_page",
                "demand_editor_ui",
                "planning_service_ui",
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
            "v14_runtime.py",
            "v17.py",
            "v17_refinements.py",
            "v17_sort_fix.py",
            "v171_performance.py",
            "v171_local_preferences.py",
            "resource_local_preferences_compat.py",
            "v18_fixes.py",
            "v18_single_scroll.py",
            "v18_calendar_sizing.py",
            "v18_workflow_fixes.py",
            "demand_legacy_cleanup.py",
            "demand_service_ui.py",
            "segment_navigation_compat.py",
            "segment_editor_compat.py",
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

    def test_quick_shift_ui_registers_cell_action_without_versioned_rewrite(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "app" / "quick_shift_ui.py").read_text(
            encoding="utf-8"
        )

        self.assertIn('MODE_QUICK = "quick"', source)
        self.assertIn('MODE_SEGMENT = "segment"', source)
        self.assertIn('MODE_QUICK: "Quart rapide"', source)
        self.assertIn('MODE_SEGMENT: "Segment existant"', source)
        self.assertIn("QuickShiftService(", source)
        self.assertIn(
            "register_operational_planning_cell_shift_opener(open_cell_shift_dialog)",
            source,
        )
        self.assertNotIn("PlannerUI.open_quick_allocation =", source)
        self.assertNotIn("v17._", source)

    def test_cell_plus_uses_explicit_non_versioned_action_boundary(self) -> None:
        app_dir = Path(__file__).resolve().parents[1] / "app"
        row_source = (app_dir / "operational_planning_resource_row.py").read_text(
            encoding="utf-8"
        )
        action_source = (app_dir / "operational_planning_cell_action.py").read_text(
            encoding="utf-8"
        )

        self.assertFalse((app_dir / "v17.py").exists())
        self.assertIn(
            "from .operational_planning_cell_action import open_operational_planning_cell_shift",
            row_source,
        )
        self.assertIn("open_operational_planning_cell_shift(", row_source)
        self.assertIn("register_operational_planning_cell_shift_opener", action_source)
        self.assertNotIn("ui.label(\"Planifier rapidement un quart\")", row_source)

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
        self.assertIn("capture_excel_allocation_commands()", source)
        self.assertIn("install_excel_allocation_service_entrypoints(", source)
        for callback in (
            "create_manual=_create_manual_via_service",
            "update_manual=_update_manual_via_service",
            "release_manual=_release_manual_via_service",
            "delete_manual=_delete_manual_via_service",
            "assign_segment=_assign_segment_via_service",
        ):
            self.assertIn(callback, source)
        self.assertNotIn("v15_engine.create_manual_allocation =", source)
        self.assertNotIn("v16._assign_segment =", source)

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
