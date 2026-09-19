from __future__ import annotations

from app.application.security import AuthPrincipal, ROLE_ADMIN
from app.server.security import static_auth_resolver


TEST_ADMIN_AUTH_RESOLVER = static_auth_resolver(
    AuthPrincipal.from_roles(
        local_user_id=None,
        issuer="urn:resourceplanner:test",
        subject="explicit-test-admin",
        display_name="Administrateur de test explicite",
        email=None,
        roles=(ROLE_ADMIN,),
        auth_mode="test",
    )
)
