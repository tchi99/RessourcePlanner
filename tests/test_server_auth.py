from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.application.security import (
    PERMISSION_READ,
    ROLE_ADMIN,
    ROLE_PROJECT_MANAGER,
    ROLE_TECHNICIAN,
    AuthPrincipal,
)
from app.server import create_api_app
from app.server.security import static_auth_resolver


def principal(role: str, *, name: str = "Utilisateur test") -> AuthPrincipal:
    return AuthPrincipal.from_roles(
        local_user_id="user-1",
        issuer="urn:test",
        subject="subject-1",
        display_name=name,
        email=None,
        roles=(role,),
        auth_mode="test",
    )


class ServerAuthTests(unittest.TestCase):
    def test_auth_me_returns_effective_identity_and_permissions(self) -> None:
        app = create_api_app(
            "sqlite+pysqlite:///:memory:",
            auth_resolver=static_auth_resolver(principal(ROLE_TECHNICIAN)),
        )
        with TestClient(app) as client:
            response = client.get("/api/v1/auth/me")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["roles"], [ROLE_TECHNICIAN])
        self.assertEqual(payload["permissions"], [PERMISSION_READ])
        self.assertEqual(payload["auth_mode"], "test")

    def test_missing_principal_returns_structured_401(self) -> None:
        app = create_api_app(
            "sqlite+pysqlite:///:memory:",
            auth_resolver=static_auth_resolver(None),
        )
        with TestClient(app) as client:
            response = client.get("/api/v1/auth/me")
            health = client.get("/health")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "authentication_required")
        self.assertEqual(health.status_code, 200)

    def test_technician_can_read_but_cannot_sync_projects(self) -> None:
        app = create_api_app(
            "sqlite+pysqlite:///:memory:",
            auth_resolver=static_auth_resolver(principal(ROLE_TECHNICIAN)),
        )
        with TestClient(app) as client:
            status_response = client.get("/api/v1/integrations/acumatica")
            sync_response = client.post("/api/v1/integrations/acumatica/projects/sync")

        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(sync_response.status_code, 403)
        self.assertEqual(sync_response.json()["error"]["code"], "permission_denied")
        self.assertEqual(
            sync_response.json()["error"]["context"]["required_permission"],
            "sync_projects",
        )

    def test_admin_passes_authorization_before_unconfigured_integration_error(self) -> None:
        app = create_api_app(
            "sqlite+pysqlite:///:memory:",
            auth_resolver=static_auth_resolver(principal(ROLE_ADMIN)),
        )
        with TestClient(app) as client:
            response = client.post("/api/v1/integrations/acumatica/projects/sync")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "acumatica_not_configured")

    def test_project_manager_cannot_mutate_resource_administration(self) -> None:
        app = create_api_app(
            "sqlite+pysqlite:///:memory:",
            auth_resolver=static_auth_resolver(principal(ROLE_PROJECT_MANAGER)),
        )
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/resources",
                headers={"Idempotency-Key": "test-key"},
                json={
                    "name": "Resource test",
                    "email": None,
                    "resource_class": "Programmation",
                    "competencies": None,
                    "note": None,
                    "active": True,
                    "sort_order": 0,
                    "external_id": None,
                },
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "permission_denied")

    def test_future_mutating_api_route_is_denied_before_falling_through(self) -> None:
        app = create_api_app(
            "sqlite+pysqlite:///:memory:",
            auth_resolver=static_auth_resolver(principal(ROLE_ADMIN)),
        )
        with TestClient(app) as client:
            response = client.post("/api/v1/not-yet-classified")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["context"]["required_permission"], "__unassigned_mutation__")


if __name__ == "__main__":
    unittest.main()
