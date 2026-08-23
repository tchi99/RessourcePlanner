from __future__ import annotations

from pathlib import Path
import unittest

from app.runtime_composition import composition_manifest


class DemandEditorUIArchitectureTests(unittest.TestCase):
    @staticmethod
    def _source(filename: str) -> str:
        root = Path(__file__).resolve().parents[1]
        return (root / "app" / filename).read_text(encoding="utf-8")

    def test_explicit_editor_owns_create_and_edit_dialogs(self) -> None:
        source = self._source("demand_editor_ui.py")

        self.assertIn("def _request_dialog(", source)
        self.assertIn("demand_service(self.repo).modify", source)
        self.assertIn("self.repo.create_demand(payload(), submit=False)", source)
        self.assertIn("self.repo.create_demand(payload(), submit=True)", source)
        self.assertIn(
            "ui_module.PlannerUI.open_new_request_dialog = _open_new_request_dialog",
            source,
        )
        self.assertIn(
            "ui_module.PlannerUI.open_edit_request_dialog = _open_edit_request_dialog",
            source,
        )

    def test_legacy_modules_no_longer_define_or_install_demand_form(self) -> None:
        features = self._source("features.py")
        refinements = self._source("v15_refinements.py")

        for source in (features, refinements):
            self.assertNotIn("def _request_dialog(", source)
            self.assertNotIn("def _open_new_request_dialog(", source)
            self.assertNotIn("def _open_edit_request_dialog(", source)
            self.assertNotIn("PlannerUI.open_new_request_dialog =", source)
            self.assertNotIn("PlannerUI.open_edit_request_dialog =", source)

        self.assertNotIn("def _project_data(", features)
        self.assertNotIn("features._project_data", refinements)
        self.assertNotIn("demand_service(self.repo).modify", refinements)

    def test_editor_is_installed_after_legacy_layers_before_application_overlays(self) -> None:
        names = [step.name for step in composition_manifest()]

        self.assertLess(names.index("v18_refinements"), names.index("demand_editor_ui"))
        self.assertLess(names.index("location_projection"), names.index("demand_editor_ui"))
        self.assertLess(names.index("demand_editor_ui"), names.index("planning_service_ui"))
        self.assertLess(names.index("demand_editor_ui"), names.index("demand_service_ui"))

    def test_editor_does_not_depend_on_legacy_features_form_helpers(self) -> None:
        source = self._source("demand_editor_ui.py")

        self.assertNotIn("from . import features", source)
        self.assertNotIn("features._project_data", source)
        self.assertIn("def _project_data(", source)


if __name__ == "__main__":
    unittest.main()
