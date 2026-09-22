from __future__ import annotations

from app.application.security import AuthPrincipal, ROLE_ADMIN, ROLE_PROJECT_MANAGER
from app.server.security import static_auth_resolver


def test_admin_auth_resolver(display_name: str = "Administrateur de test explicite"):
    return static_auth_resolver(
        AuthPrincipal.from_roles(
            local_user_id=None,
            issuer="urn:resourceplanner:test",
            subject="explicit-test-admin",
            display_name=display_name,
            email=None,
            roles=(ROLE_ADMIN,),
            auth_mode="test",
        )
    )


TEST_ADMIN_AUTH_RESOLVER = test_admin_auth_resolver()


def test_project_manager_auth_resolver(
    display_name: str = "Chargé de projet de test explicite",
):
    return static_auth_resolver(
        AuthPrincipal.from_roles(
            local_user_id=None,
            issuer="urn:resourceplanner:test",
            subject="explicit-test-project-manager",
            display_name=display_name,
            email=None,
            roles=(ROLE_PROJECT_MANAGER,),
            auth_mode="test",
        )
    )


TEST_PROJECT_MANAGER_AUTH_RESOLVER = test_project_manager_auth_resolver()
