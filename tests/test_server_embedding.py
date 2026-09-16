from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.server.embedding import (
    FRAME_ANCESTORS_ENV,
    OIDC_COOKIE_SAMESITE_ENV,
    EmbeddingSettings,
    parse_frame_ancestors,
)
from app.server.runtime import (
    AUTH_MODE_ENV,
    DATABASE_URL_ENV,
    OIDC_CLIENT_ID_ENV,
    OIDC_DISCOVERY_URL_ENV,
    OIDC_REDIRECT_URI_ENV,
    OIDC_SECURE_COOKIE_ENV,
    ServerConfigurationError,
    ServerSettings,
    create_configured_app,
)


class ServerEmbeddingTests(unittest.TestCase):
    def test_embedding_is_denied_by_default_with_csp(self) -> None:
        settings = ServerSettings(database_url="sqlite+pysqlite:///:memory:")
        app = create_configured_app(settings)

        with TestClient(app) as client:
            response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("content-security-policy"),
            "frame-ancestors 'none'",
        )

    def test_explicit_https_parent_origins_are_normalized(self) -> None:
        sources = parse_frame_ancestors(
            "'self', https://erp.example.test/ https://portal.example.test:8443"
        )
        self.assertEqual(
            sources,
            ("'self'", "https://erp.example.test", "https://portal.example.test:8443"),
        )

    def test_wildcard_path_and_non_https_remote_parent_are_rejected(self) -> None:
        invalid_values = (
            "*",
            "https://erp.example.test/path",
            "http://erp.example.test",
            "'none' https://erp.example.test",
        )
        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_frame_ancestors(value)

    def test_loopback_http_parent_is_allowed_for_local_embedding_tests(self) -> None:
        self.assertEqual(
            parse_frame_ancestors("http://localhost:3000"),
            ("http://localhost:3000",),
        )

    def test_configured_parent_is_emitted_by_runtime(self) -> None:
        settings = ServerSettings(
            database_url="sqlite+pysqlite:///:memory:",
            embedding=EmbeddingSettings(frame_ancestors=("https://erp.example.test",)),
        )
        app = create_configured_app(settings)

        with TestClient(app) as client:
            response = client.get("/health")

        self.assertEqual(
            response.headers.get("content-security-policy"),
            "frame-ancestors https://erp.example.test",
        )

    def test_environment_parses_explicit_frame_ancestors(self) -> None:
        settings = ServerSettings.from_environment(
            {
                DATABASE_URL_ENV: "sqlite+pysqlite:///:memory:",
                FRAME_ANCESTORS_ENV: "https://erp.example.test https://portal.example.test",
            }
        )
        self.assertEqual(
            settings.embedding.frame_ancestors,
            ("https://erp.example.test", "https://portal.example.test"),
        )

    def test_samesite_none_requires_secure_oidc_cookie(self) -> None:
        base = {
            DATABASE_URL_ENV: "sqlite+pysqlite:///:memory:",
            AUTH_MODE_ENV: "oidc",
            OIDC_DISCOVERY_URL_ENV: "https://identity.example.invalid/.well-known/openid-configuration",
            OIDC_CLIENT_ID_ENV: "resourceplanner",
            OIDC_REDIRECT_URI_ENV: "https://planner.example.invalid/api/v1/auth/callback",
            OIDC_COOKIE_SAMESITE_ENV: "none",
        }
        with self.assertRaises(ServerConfigurationError) as caught:
            ServerSettings.from_environment(
                {**base, OIDC_SECURE_COOKIE_ENV: "false"}
            )
        self.assertIn(OIDC_COOKIE_SAMESITE_ENV, str(caught.exception))
        self.assertIn(OIDC_SECURE_COOKIE_ENV, str(caught.exception))

    def test_samesite_none_is_allowed_with_secure_oidc_cookie(self) -> None:
        settings = ServerSettings.from_environment(
            {
                DATABASE_URL_ENV: "sqlite+pysqlite:///:memory:",
                AUTH_MODE_ENV: "oidc",
                OIDC_DISCOVERY_URL_ENV: "https://identity.example.invalid/.well-known/openid-configuration",
                OIDC_CLIENT_ID_ENV: "resourceplanner",
                OIDC_REDIRECT_URI_ENV: "https://planner.example.invalid/api/v1/auth/callback",
                OIDC_COOKIE_SAMESITE_ENV: "none",
                OIDC_SECURE_COOKIE_ENV: "true",
            }
        )
        self.assertTrue(settings.oidc_secure_cookie)
        self.assertEqual(settings.embedding.oidc_cookie_samesite, "none")

    def test_invalid_samesite_value_is_rejected(self) -> None:
        with self.assertRaises(ServerConfigurationError):
            ServerSettings.from_environment(
                {
                    DATABASE_URL_ENV: "sqlite+pysqlite:///:memory:",
                    OIDC_COOKIE_SAMESITE_ENV: "cross-site",
                }
            )


if __name__ == "__main__":
    unittest.main()
