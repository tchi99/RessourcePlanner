from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class EmergencyOverrideFrontendContractTests(unittest.TestCase):
    def test_client_uses_explicit_emergency_plan_endpoint(self) -> None:
        source = (ROOT / "frontend" / "src" / "demandWorkflowApi.ts").read_text(
            encoding="utf-8"
        )
        self.assertIn('"emergency-plan"', source)
        self.assertIn("export function emergencyPlanDemand", source)

    def test_workspace_gates_emergency_surface_on_approval_permission(self) -> None:
        source = (ROOT / "frontend" / "src" / "DemandsWorkspace.tsx").read_text(
            encoding="utf-8"
        )
        self.assertIn('can("approve_demands")', source)
        self.assertIn("EmergencyOverridePage", source)
        self.assertIn("Urgence", source)

    def test_emergency_page_requires_reason_and_warns_coordinator(self) -> None:
        source = (ROOT / "frontend" / "src" / "EmergencyOverridePage.tsx").read_text(
            encoding="utf-8"
        )
        self.assertIn("Planifier en urgence", source)
        self.assertIn("coordonnateur doit être informé", source.lower())
        self.assertIn("Justification de l’urgence (requise)", source)
        self.assertIn("emergency_override_active", source)
        self.assertIn("la demande demeurera Soumise", source)

    def test_planning_marks_shifts_from_active_override(self) -> None:
        source = (ROOT / "frontend" / "src" / "PlanningPage.tsx").read_text(
            encoding="utf-8"
        )
        self.assertIn("emergency_override_active", source)
        self.assertIn("Dérogation urgente", source)
        self.assertIn("régularisation requise", source)


if __name__ == "__main__":
    unittest.main()
