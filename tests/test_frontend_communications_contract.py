from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "frontend" / "src" / "App.tsx"
PAGE = ROOT / "frontend" / "src" / "CommunicationsPage.tsx"
API = ROOT / "frontend" / "src" / "communicationsApi.ts"
MAIN = ROOT / "frontend" / "src" / "main.tsx"


class FrontendCommunicationsContractTests(unittest.TestCase):
    def test_navigation_is_permission_gated_and_page_is_wired(self) -> None:
        app = APP.read_text(encoding="utf-8")
        self.assertIn('permission: "manage_communications"', app)
        self.assertIn('import CommunicationsPage from "./CommunicationsPage"', app)
        self.assertIn('<CommunicationsPage />', app)

    def test_page_keeps_manual_review_and_no_send_language(self) -> None:
        page = PAGE.read_text(encoding="utf-8")
        self.assertIn("Préparer le lot", page)
        self.assertIn("Approuver", page)
        self.assertIn("Confirmer communiqué", page)
        self.assertIn("Aucun message n’a été envoyé", page)
        self.assertIn("included", page)

    def test_api_targets_only_controlled_communication_routes(self) -> None:
        api = API.read_text(encoding="utf-8")
        self.assertIn("/api/v1/communications/contacts", api)
        self.assertIn("/api/v1/communications/preview", api)
        self.assertIn("/api/v1/communications/batches", api)
        self.assertNotIn("graph.microsoft", api.lower())
        self.assertNotIn("outlook", api.lower())

    def test_stylesheet_is_loaded(self) -> None:
        main = MAIN.read_text(encoding="utf-8")
        self.assertIn('import "./communications.css"', main)


if __name__ == "__main__":
    unittest.main()
