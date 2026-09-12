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
    ACUMATICA_STATUS_FIELD_ENV,
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

    def test_complete_environment_builds_configurable_acumatica_settings(self) -> None:
        settings = ServerSettings.from_environment(
            {
                DATABASE_URL_ENV: "sqlite+pysqlite:///:memory:",
                ACUMATICA_BASE_URL_ENV: "https://erp.example.test/Instance",
                ACUMATICA_ACCESS_TOKEN_ENV: "secret-token",
                ACUMATICA_ENDPOINT_ENV: "RP",
                ACUMATICA_VERSION_ENV: "1.0.0",
                ACUMATICA_ENTITY_ENV: "RPProject",
                ACUMATICA_NUMBER_FIELD_ENV: "Nbr",
                ACUMATICA_NAME_FIELD_ENV: "Label",
                ACUMATICA_CLIENT_FIELD_ENV: "Account",
                ACUMATICA_MANAGER_FIELD_ENV: "Owner",
                ACUMATICA_STATUS_FIELD_ENV: "State",
                ACUMATICA_PAGE_SIZE_ENV: "75",
            }
        )
        assert settings.acumatica is not None
        self.assertEqual(settings.acumatica.endpoint, "RP")
        self.assertEqual(settings.acumatica.version, "1.0.0")
        self.assertEqual(settings.acumatica.entity, "RPProject")
        self.assertEqual(settings.acumatica.number_field, "Nbr")
        self.assertEqual(settings.acumatica.page_size, 75)
        self.assertNotIn("secret-token", repr(settings))
        self.assertNotIn("secret-token", repr(settings.acumatica))

    def test_partial_acumatica_configuration_is_rejected(self) -> None:
        with self.assertRaises(ServerConfigurationError) as raised:
            ServerSettings.from_environment(
                {
                    DATABASE_URL_ENV: "sqlite+pysqlite:///:memory:",
                    ACUMATICA_BASE_URL_ENV: "https://erp.example.test",
                    ACUMATICA_VERSION_ENV: "25.200.001",
                }
            )
        self.assertIn(ACUMATICA_ACCESS_TOKEN_ENV, str(raised.exception))

    def test_invalid_acumatica_page_size_is_rejected(self) -> None:
        for value in ("0", "1001", "abc"):
            with self.subTest(value=value):
                with self.assertRaises(ServerConfigurationError):
                    ServerSettings.from_environment(
                        {
                            DATABASE_URL_ENV: "sqlite+pysqlite:///:memory:",
                            ACUMATICA_BASE_URL_ENV: "https://erp.example.test",
                            ACUMATICA_ACCESS_TOKEN_ENV: "token",
                            ACUMATICA_VERSION_ENV: "25.200.001",
                            ACUMATICA_PAGE_SIZE_ENV: value,
                        }
                    )


if __name__ == "__main__":
    unittest.main()
