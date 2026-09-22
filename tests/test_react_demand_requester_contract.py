from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReactDemandRequesterContractTests(unittest.TestCase):
    def test_api_uses_stable_requester_identity(self) -> None:
        api = (ROOT / "frontend" / "src" / "api.ts").read_text(encoding="utf-8")

        self.assertIn("export type DemandRequesterReadModel", api)
        self.assertIn("requester_user_id: string | null", api)
        self.assertIn("requester_user_id?: string | null", api)
        self.assertIn('"/api/v1/demand-requesters"', api)
        self.assertNotIn("  requester: string | null;\n  request_type?: string;", api)

    def test_demands_page_replaces_free_text_with_role_aware_selector(self) -> None:
        page = (ROOT / "frontend" / "src" / "DemandsPage.tsx").read_text(
            encoding="utf-8"
        )

        self.assertIn("canDelegateRequester", page)
        self.assertIn('role === "COORDINATOR" || role === "ADMIN"', page)
        self.assertIn('setField("requester_user_id"', page)
        self.assertIn("requester.display_name", page)
        self.assertIn("principal?.display_name", page)
        self.assertIn("Demande historique : identité canonique non attribuée.", page)
        self.assertNotIn('placeholder="Nom du demandeur"', page)

    def test_history_contract_exposes_stable_actor_identity(self) -> None:
        history_api = (ROOT / "frontend" / "src" / "demandHistoryApi.ts").read_text(
            encoding="utf-8"
        )

        self.assertIn("actor_user_id: string | null", history_api)


if __name__ == "__main__":
    unittest.main()
