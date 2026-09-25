from __future__ import annotations

import unittest

from app.server.runtime import (
    ACUMATICA_ACCESS_TOKEN_ENV,
    ACUMATICA_BASE_URL_ENV,
    ACUMATICA_CLIENT_FIELD_ENV,
    ACUMATICA_ENDPOINT_ENV,
    ACUMATICA_ENTITY_ENV,
    ACUMATICA_MANAGER_FIELD_ENV,
    ACUMATICA_NAME_FIELD_ENV,
    ACUMATICA_NUMBER_FIELD_ENV,
    ACUMATICA_PAGE_SIZE_ENV,
    ACUMATICA_PASSWORD_ENV,
    ACUMATICA_STATUS_FIELD_ENV,
    ACUMATICA_USERNAME_ENV,
    ACUMATICA_TIMEOUT_SECONDS_ENV,
    ACUMATICA_VERSION_ENV,
    DATABASE_URL_ENV,
    ServerConfigurationError,
    ServerSettings,
)


class ServerAcumaticaRuntimeTests(unittest.TestCase):
    def test_acumatica_is_optional_for_local_runtime(self) -> None:
        settings = ServerSettings.from_environment(
            {DATABASE_URL_ENV: "sqlite+pysqlite:///:memory:"}
        )
        self.assertIsNone(settings.acumatica)

    def test_base_url_builds_basic_odata_project_settings(self) -> None:
        settings = ServerSettings.from_environment(
            {
                DATABASE_URL_ENV: "sqlite+pysqlite:///:memory:",
                ACUMATICA_BASE_URL_ENV: "https://erp.example.test/Instance",
                ACUMATICA_USERNAME_ENV: "odata-user",
                ACUMATICA_PASSWORD_ENV: "dummy-passphrase",
                ACUMATICA_PAGE_SIZE_ENV: "25",
                ACUMATICA_TIMEOUT_SECONDS_ENV: "12.5",
            }
        )

        assert settings.acumatica is not None
        self.assertEqual(settings.acumatica.base_url, "https://erp.example.test/Instance")
        self.assertEqual(settings.acumatica.feed_path, "/oDATA/RP_Projects")
        self.assertEqual(settings.acumatica.page_size, 25)
        self.assertEqual(settings.acumatica.timeout_seconds, 12.5)
        self.assertEqual(
            settings.acumatica.safe_summary(),
            {
                "protocol": "odata",
                "feed_path": "/oDATA/RP_Projects",
                "authentication": "basic",
                "pagination": {
                    "mode": "top_skip",
                    "orderby": "ProjectId asc",
                    "page_size": 25,
                },
            },
        )
        diagnostic = repr(settings) + repr(settings.acumatica) + str(settings.acumatica.safe_summary())
        self.assertNotIn("odata-user", diagnostic)
        self.assertNotIn("dummy-passphrase", diagnostic)

    def test_legacy_rest_configuration_is_not_required_by_odata_runtime(self) -> None:
        settings = ServerSettings.from_environment(
            {
                DATABASE_URL_ENV: "sqlite+pysqlite:///:memory:",
                ACUMATICA_BASE_URL_ENV: "https://erp.example.test/Instance",
                ACUMATICA_USERNAME_ENV: "odata-user",
                ACUMATICA_PASSWORD_ENV: "dummy-passphrase",
                ACUMATICA_ACCESS_TOKEN_ENV: "legacy-secret-token",
                ACUMATICA_ENDPOINT_ENV: "LegacyEndpoint",
                ACUMATICA_VERSION_ENV: "25.200.001",
                ACUMATICA_ENTITY_ENV: "LegacyProject",
                ACUMATICA_NUMBER_FIELD_ENV: "LegacyNumber",
                ACUMATICA_NAME_FIELD_ENV: "LegacyName",
                ACUMATICA_CLIENT_FIELD_ENV: "LegacyClient",
                ACUMATICA_MANAGER_FIELD_ENV: "LegacyManager",
                ACUMATICA_STATUS_FIELD_ENV: "LegacyStatus",
            }
        )

        assert settings.acumatica is not None
        self.assertEqual(settings.acumatica.feed_path, "/oDATA/RP_Projects")
        self.assertEqual(settings.acumatica.page_size, 100)
        self.assertEqual(settings.acumatica.timeout_seconds, 30.0)
        diagnostic = repr(settings) + repr(settings.acumatica) + str(settings.acumatica.safe_summary())
        self.assertNotIn("legacy-secret-token", diagnostic)
        self.assertNotIn("odata-user", diagnostic)
        self.assertNotIn("dummy-passphrase", diagnostic)
        self.assertNotIn("LegacyEndpoint", diagnostic)
        self.assertNotIn("LegacyProject", diagnostic)

    def test_legacy_rest_values_without_base_url_do_not_activate_integration(self) -> None:
        settings = ServerSettings.from_environment(
            {
                DATABASE_URL_ENV: "sqlite+pysqlite:///:memory:",
                ACUMATICA_ACCESS_TOKEN_ENV: "legacy-secret-token",
                ACUMATICA_VERSION_ENV: "25.200.001",
                ACUMATICA_ENTITY_ENV: "Project",
            }
        )
        self.assertIsNone(settings.acumatica)

    def test_invalid_acumatica_timeout_is_rejected(self) -> None:
        for value in ("0", "-1", "121", "abc"):
            with self.subTest(value=value):
                with self.assertRaises(ServerConfigurationError):
                    ServerSettings.from_environment(
                        {
                            DATABASE_URL_ENV: "sqlite+pysqlite:///:memory:",
                            ACUMATICA_BASE_URL_ENV: "https://erp.example.test",
                            ACUMATICA_USERNAME_ENV: "odata-user",
                            ACUMATICA_PASSWORD_ENV: "dummy-passphrase",
                            ACUMATICA_TIMEOUT_SECONDS_ENV: value,
                        }
                    )


    def test_basic_credentials_are_required_together_when_acumatica_is_enabled(self) -> None:
        cases = (
            {},
            {ACUMATICA_USERNAME_ENV: "odata-user"},
            {ACUMATICA_PASSWORD_ENV: "dummy-passphrase"},
        )
        for credentials in cases:
            with self.subTest(credentials=tuple(credentials)):
                with self.assertRaises(ServerConfigurationError):
                    ServerSettings.from_environment(
                        {
                            DATABASE_URL_ENV: "sqlite+pysqlite:///:memory:",
                            ACUMATICA_BASE_URL_ENV: "https://erp.example.test",
                            **credentials,
                        }
                    )

    def test_invalid_odata_page_size_is_rejected(self) -> None:
        for value in ("0", "-1", "10001", "abc"):
            with self.subTest(value=value):
                with self.assertRaises(ServerConfigurationError):
                    ServerSettings.from_environment(
                        {
                            DATABASE_URL_ENV: "sqlite+pysqlite:///:memory:",
                            ACUMATICA_BASE_URL_ENV: "https://erp.example.test",
                            ACUMATICA_USERNAME_ENV: "odata-user",
                            ACUMATICA_PASSWORD_ENV: "dummy-passphrase",
                            ACUMATICA_PAGE_SIZE_ENV: value,
                        }
                    )


if __name__ == "__main__":
    unittest.main()
