from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReactDemandPeriodsContractTests(unittest.TestCase):
    def test_workspace_exposes_periods_without_replacing_demand_editor(self) -> None:
        workspace = (ROOT / "frontend" / "src" / "DemandsWorkspace.tsx").read_text(
            encoding="utf-8"
        )
        app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
        main = (ROOT / "frontend" / "src" / "main.tsx").read_text(encoding="utf-8")

        self.assertIn("<DemandsPage />", workspace)
        self.assertIn("<DemandPeriodsPage />", workspace)
        self.assertIn("Périodes & alternatives", workspace)
        self.assertIn("<DemandsWorkspace />", app)
        self.assertIn('import "./demand-periods.css"', main)

    def test_api_client_uses_existing_period_and_selection_endpoints(self) -> None:
        source = (ROOT / "frontend" / "src" / "api.ts").read_text(encoding="utf-8")

        self.assertIn("getDemandPeriods", source)
        self.assertIn("replaceDemandPeriods", source)
        self.assertIn("selectDemandAlternative", source)
        self.assertIn("/periods`,", source)
        self.assertIn("/alternative-groups/${encodeURIComponent(alternativeGroup)}/selection", source)
        self.assertIn("period_id: periodId", source)

    def test_editor_models_cumulative_and_exclusive_alternative_periods(self) -> None:
        source = (ROOT / "frontend" / "src" / "DemandPeriodsPage.tsx").read_text(
            encoding="utf-8"
        )

        self.assertIn('kind: "CUMULATIVE"', source)
        self.assertIn('kind: "ALTERNATIVE"', source)
        self.assertIn("nextAlternativeGroup(periods)", source)
        self.assertIn("Le groupe ${group} doit contenir au moins deux options.", source)
        self.assertIn("Une seule option d'un même groupe est retenue", source)
        self.assertIn("Retenir cette option", source)
        self.assertIn("disabled={saving || dirty || period.selected}", source)

    def test_period_save_preserves_backend_authority_and_reapproval_signal(self) -> None:
        source = (ROOT / "frontend" / "src" / "DemandPeriodsPage.tsx").read_text(
            encoding="utf-8"
        )

        self.assertIn("await replaceDemandPeriods(selectedDemand.number, payload)", source)
        self.assertIn("result.reapproval_required", source)
        self.assertIn("le plan approuvé précédent reste inchangé", source)
        self.assertIn("await selectDemandAlternative(selectedDemand.number, group, periodId)", source)
        self.assertNotIn("projected_hours_without_double_counting", source)


if __name__ == "__main__":
    unittest.main()
