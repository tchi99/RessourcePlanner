from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "frontend" / "src" / "ErpUserDirectoryPanel.tsx"
API = ROOT / "frontend" / "src" / "erpUserAdminApi.ts"
USER_PAGE = ROOT / "frontend" / "src" / "UserAdminPage.tsx"


class ReactErpUserAdminContractTests(unittest.TestCase):
    def test_admin_page_surfaces_distinct_erp_directory(self) -> None:
        page = PAGE.read_text(encoding="utf-8")
        user_page = USER_PAGE.read_text(encoding="utf-8")

        self.assertIn("Annuaire RP_Users", page)
        self.assertIn("UserID", page)
        self.assertIn("EmployeID / ressource", page)
        self.assertIn("ERP User", page)
        self.assertIn("ERP Employé", page)
        self.assertIn("Activation RessourcePlanner", page)
        self.assertIn("Non résolu (#223)", page)
        self.assertIn("<ErpUserDirectoryPanel roleCatalog={roleCatalog}", user_page)

    def test_api_uses_erp_directory_without_app_user_creation_contract(self) -> None:
        api = API.read_text(encoding="utf-8")
        page = PAGE.read_text(encoding="utf-8")

        self.assertIn('"/api/v1/admin/erp-users"', api)
        self.assertIn('"/api/v1/integrations/acumatica/users/sync"', api)
        self.assertIn("aucun compte OIDC n’est créé", page)
        self.assertNotIn("issuer:", page)
        self.assertNotIn("subject:", page)


if __name__ == "__main__":
    unittest.main()
