from __future__ import annotations

import unittest

from app.server.runtime import (
    DATABASE_URL_ENV,
    M365_CLIENT_ID_ENV,
    M365_CLIENT_SECRET_ENV,
    M365_MAILBOX_ENV,
    M365_TENANT_ID_ENV,
    ServerConfigurationError,
    ServerSettings,
)


TEST_MAILBOX = "planning" + chr(64) + "example.test"


class Microsoft365RuntimeTests(unittest.TestCase):
    def test_m365_is_optional_by_default(self) -> None:
        settings = ServerSettings.from_environment(
            {DATABASE_URL_ENV: "sqlite+pysqlite:///:memory:"}
        )
        self.assertIsNone(settings.m365)

    def test_partial_m365_configuration_is_rejected(self) -> None:
        with self.assertRaises(ServerConfigurationError) as caught:
            ServerSettings.from_environment(
                {
                    DATABASE_URL_ENV: "sqlite+pysqlite:///:memory:",
                    M365_TENANT_ID_ENV: "tenant-id",
                    M365_CLIENT_ID_ENV: "client-id",
                }
            )
        self.assertIn(M365_CLIENT_SECRET_ENV, str(caught.exception))
        self.assertIn(M365_MAILBOX_ENV, str(caught.exception))

    def test_complete_m365_configuration_builds_secret_safe_settings(self) -> None:
        settings = ServerSettings.from_environment(
            {
                DATABASE_URL_ENV: "sqlite+pysqlite:///:memory:",
                M365_TENANT_ID_ENV: "tenant-id",
                M365_CLIENT_ID_ENV: "client-id",
                M365_CLIENT_SECRET_ENV: "test",
                M365_MAILBOX_ENV: TEST_MAILBOX,
            }
        )
        self.assertIsNotNone(settings.m365)
        assert settings.m365 is not None
        self.assertEqual(settings.m365.mailbox, TEST_MAILBOX)
        self.assertEqual(settings.m365.safe_summary()["provider"], "microsoft_graph")
        self.assertNotIn("client_secret='test'", repr(settings))
        self.assertNotIn("client_secret='test'", repr(settings.m365))


if __name__ == "__main__":
    unittest.main()
