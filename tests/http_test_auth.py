from __future__ import annotations

from app.application.security import AuthPrincipal, ROLE_ADMIN, ROLE_COORDINATOR, ROLE_PROJECT_MANAGER
from app.server.security import static_auth_resolver
from tests.approval_test_support import (
    TEST_ADMIN_USER_ID,
    TEST_COORDINATOR_USER_ID,
)


def test_admin_auth_resolver(display_name: str = "Administrateur de test explicite"):
    return static_auth_resolver(
        AuthPrincipal.from_roles(
            local_user_id=TEST_ADMIN_USER_ID,
            issuer="urn:resourceplanner:test",
            subject="explicit-test-admin",
            display_name=display_name,
            email=None,
            roles=(ROLE_ADMIN,),
            auth_mode="test",
        )
    )


TEST_ADMIN_AUTH_RESOLVER = test_admin_auth_resolver()


def test_coordinator_auth_resolver(
    display_name: str = "Coordonnateur de test explicite",
):
    return static_auth_resolver(
        AuthPrincipal.from_roles(
            local_user_id=TEST_COORDINATOR_USER_ID,
            issuer="urn:resourceplanner:test",
            subject="explicit-test-coordinator",
            display_name=display_name,
            email=None,
            roles=(ROLE_COORDINATOR,),
            auth_mode="test",
        )
    )


TEST_COORDINATOR_AUTH_RESOLVER = test_coordinator_auth_resolver()


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
