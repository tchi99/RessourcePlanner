from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"


class ReactAuthContextContractTests(unittest.TestCase):
    def test_auth_context_loads_backend_principal_and_uses_effective_permissions(self) -> None:
        context = (FRONTEND / "AuthContext.tsx").read_text(encoding="utf-8")
        api = (FRONTEND / "auth-api.ts").read_text(encoding="utf-8")

        self.assertIn("/api/v1/auth/me", api)
        self.assertIn("permissions: string[]", api)
        self.assertIn("getCurrentPrincipal", context)
        self.assertIn("principal?.permissions.includes(permission)", context)
        self.assertNotIn("ROLE_ADMIN", context)
        self.assertNotIn("ROLE_COORDINATOR", context)

    def test_shell_displays_identity_and_hides_resource_admin_without_permission(self) -> None:
        app = (FRONTEND / "App.tsx").read_text(encoding="utf-8")

        self.assertIn('permission: "manage_resources"', app)
        self.assertIn("principal.display_name", app)
        self.assertIn("principal.roles.join", app)
        self.assertIn("authLoading", app)
        self.assertIn("authError", app)

    def test_oidc_login_and_logout_are_same_origin_server_actions(self) -> None:
        context = (FRONTEND / "AuthContext.tsx").read_text(encoding="utf-8")
        api = (FRONTEND / "auth-api.ts").read_text(encoding="utf-8")
        app = (FRONTEND / "App.tsx").read_text(encoding="utf-8")

        self.assertIn("/api/v1/auth/login", api)
        self.assertIn("/api/v1/auth/logout", api)
        self.assertIn('credentials: "include"', api)
        self.assertIn('reason.code === "authentication_required"', context)
        self.assertIn("window.location.assign(getLoginUrl())", context)
        self.assertIn("Se connecter avec Acumatica", app)
        self.assertIn("Déconnexion", app)
        self.assertIn('principal.auth_mode === "oidc"', app)
        self.assertNotIn("access_token", context)
        self.assertNotIn("id_token", context)
        self.assertNotIn("localStorage", context)
        self.assertNotIn("sessionStorage", context)

    def test_mutating_surfaces_consume_backend_permissions(self) -> None:
        projects = (FRONTEND / "ProjectsPage.tsx").read_text(encoding="utf-8")
        workspace = (FRONTEND / "DemandsWorkspace.tsx").read_text(encoding="utf-8")
        quick_shift = (FRONTEND / "QuickShiftEditor.tsx").read_text(encoding="utf-8")
        shift = (FRONTEND / "ShiftEditor.tsx").read_text(encoding="utf-8")

        self.assertIn('can("sync_projects")', projects)
        self.assertIn('can("manage_demands")', workspace)
        self.assertIn('can("approve_demands")', workspace)
        self.assertIn('can("manage_planning")', workspace)
        self.assertIn('can("manage_planning")', quick_shift)
        self.assertIn('can("manage_planning")', shift)

        combined = "\n".join((projects, workspace, quick_shift, shift))
        self.assertNotIn('roles.includes("ADMIN")', combined)
        self.assertNotIn('roles.includes("COORDINATOR")', combined)

    def test_main_wraps_application_in_auth_provider(self) -> None:
        main = (FRONTEND / "main.tsx").read_text(encoding="utf-8")
        self.assertIn("AuthProvider", main)
        self.assertIn("<AuthProvider>", main)


if __name__ == "__main__":
    unittest.main()
