from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReactRequestLinesContractTests(unittest.TestCase):
    def test_api_contract_exposes_line_identity_and_write_shape(self) -> None:
        source = (ROOT / "frontend" / "src" / "api.ts").read_text(encoding="utf-8")

        self.assertIn("export type DemandLineReadModel", source)
        self.assertIn("line_id: string", source)
        self.assertIn("required_resource_class: string | null", source)
        self.assertIn("required_competency_ids: string[]", source)
        self.assertIn("estimated_hours_source:", source)
        self.assertIn("line_mode: boolean", source)
        self.assertIn("lines: DemandLineReadModel[]", source)
        self.assertIn("export type DemandLineWrite", source)
        self.assertIn("proposed_resource_id: string | null", source)
        self.assertIn("expected_version?: number", source)

    def test_editor_supports_generation_add_duplicate_and_line_totals(self) -> None:
        source = (ROOT / "frontend" / "src" / "DemandLinesEditor.tsx").read_text(
            encoding="utf-8"
        )

        self.assertIn("Générer les lignes", source)
        self.assertIn("+ Ajouter une ligne", source)
        self.assertIn("Dupliquer", source)
        self.assertIn("Retirer", source)
        self.assertIn("Classe de ressource", source)
        self.assertIn("Compétences requises — ligne", source)
        self.assertIn("WorkPackage", source)
        self.assertIn("Tâche ERP", source)
        self.assertIn("Récapitulatif des lignes", source)
        self.assertIn("heure(s) projetées", source)
        self.assertIn("days * 8", source)
        self.assertIn("le backend demeure autoritaire", source)

    def test_demands_page_preserves_legacy_editor_and_sends_versioned_lines(self) -> None:
        source = (ROOT / "frontend" / "src" / "DemandsPage.tsx").read_text(
            encoding="utf-8"
        )

        self.assertIn("Passer aux lignes multiples", source)
        self.assertIn("Revenir au besoin simple", source)
        self.assertIn("Mode lignes enregistré", source)
        self.assertIn("lines: lines.map(demandLineWrite)", source)
        self.assertIn("expected_version: selectedDemand.version", source)
        self.assertIn("lineValidationMessage", source)
        self.assertIn("demand-flat-need-grid", source)
        self.assertIn("<DemandLinesEditor", source)

    def test_default_eight_hour_policy_is_not_written_as_explicit_line_hours(self) -> None:
        source = (ROOT / "frontend" / "src" / "DemandLinesEditor.tsx").read_text(
            encoding="utf-8"
        )

        self.assertIn("estimated_hours: hours == null", source)
        self.assertNotIn("estimated_hours: days * 8", source)
        self.assertIn("8 h par jour actif", source)


if __name__ == "__main__":
    unittest.main()
