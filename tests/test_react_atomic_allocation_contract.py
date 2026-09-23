from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"


class ReactAtomicAllocationContractTests(unittest.TestCase):
    def test_api_contract_carries_planning_version_and_mandatory_idempotency_key(self) -> None:
        api = (FRONTEND / "api.ts").read_text(encoding="utf-8")
        overallocation = (FRONTEND / "manualOverallocationApi.ts").read_text(encoding="utf-8")

        self.assertIn("planning_version: number", api)
        self.assertIn("/split", overallocation)
        self.assertIn("/duplicate", overallocation)
        self.assertIn('"Idempotency-Key": idempotencyKey', overallocation)
        self.assertIn("expected_planning_version", overallocation)
        self.assertIn("expected_approval_revision_id", overallocation)
        self.assertIn("expected_operational_version", overallocation)
        self.assertIn("csrfHeaders()", overallocation)
        self.assertIn('credentials: "include"', overallocation)

    def test_shift_editor_freezes_versions_and_key_for_network_retry(self) -> None:
        source = (FRONTEND / "ShiftEditor.tsx").read_text(encoding="utf-8")

        self.assertIn("newAtomicIdempotencyKey", source)
        self.assertIn("expectedPlanningVersion: planningVersion", source)
        self.assertIn("idempotencyKey: newAtomicIdempotencyKey()", source)
        self.assertIn("ambiguousRetry", source)
        self.assertIn("Réessayer la même commande", source)
        self.assertIn("la même clé idempotente", source)
        self.assertIn("retryPolicy", source)
        self.assertIn("getDemandDetail", source)
        self.assertIn("active_revision_id", source)
        self.assertIn("operational_version", source)

    def test_shift_editor_reuses_overallocation_choice_and_structured_conflicts(self) -> None:
        source = (FRONTEND / "ShiftEditor.tsx").read_text(encoding="utf-8")

        self.assertIn('overallocationSource === "atomic"', source)
        self.assertIn('executeAtomic("INCREASE_PLANNED")', source)
        self.assertIn('executeAtomic("KEEP_EXCEPTION")', source)
        self.assertIn('"planning_version_conflict"', source)
        self.assertIn('"operational_choice_version_conflict"', source)
        self.assertIn('"planning_authorization_unknown"', source)
        self.assertIn("onStale()", source)
        self.assertIn('can("manage_planning")', source)
        self.assertNotIn("manual_overallocation_impact", source)
        self.assertNotIn("1.20", source)

    def test_planning_page_passes_snapshot_version_and_refreshes_after_success_or_conflict(self) -> None:
        source = (FRONTEND / "PlanningPage.tsx").read_text(encoding="utf-8")

        self.assertIn("planningVersion={snapshot.planning_version}", source)
        self.assertIn("onStale={() =>", source)
        self.assertIn("Le planning a changé depuis l'ouverture du quart", source)
        self.assertIn("setRefreshKey((value) => value + 1)", source)


if __name__ == "__main__":
    unittest.main()
