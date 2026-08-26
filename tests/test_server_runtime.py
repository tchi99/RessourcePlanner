from __future__ import annotations

import unittest
from unittest.mock import patch

from app.server.runtime import (
    ACTOR_NAME_ENV,
    DATABASE_URL_ENV,
    HOST_ENV,
    LOG_LEVEL_ENV,
    PORT_ENV,
    ServerConfigurationError,
    ServerSettings,
    main,
    run_server,
)


class ServerRuntimeTests(unittest.TestCase):
    def test_database_url_is_required(self) -> None:
        with self.assertRaises(ServerConfigurationError) as caught:
            ServerSettings.from_environment({})
        self.assertIn(DATABASE_URL_ENV, str(caught.exception))

    def test_defaults_are_safe_for_local_startup(self) -> None:
        settings = ServerSettings.from_environment(
            {DATABASE_URL_ENV: "sqlite+pysqlite:///:memory:"}
        )
        self.assertEqual(settings.host, "127.0.0.1")
        self.assertEqual(settings.port, 8000)
        self.assertEqual(settings.log_level, "info")
        self.assertEqual(settings.actor_name, "api")

    def test_environment_overrides_server_values(self) -> None:
        settings = ServerSettings.from_environment(
            {
                DATABASE_URL_ENV: "sqlite+pysqlite:///:memory:",
                HOST_ENV: "0.0.0.0",
                PORT_ENV: "8123",
                LOG_LEVEL_ENV: "WARNING",
                ACTOR_NAME_ENV: "local-admin",
            }
        )
        self.assertEqual(settings.host, "0.0.0.0")
        self.assertEqual(settings.port, 8123)
        self.assertEqual(settings.log_level, "warning")
        self.assertEqual(settings.actor_name, "local-admin")

    def test_invalid_port_is_rejected(self) -> None:
        for value in ("abc", "0", "65536"):
            with self.subTest(value=value):
                with self.assertRaises(ServerConfigurationError):
                    ServerSettings.from_environment(
                        {
                            DATABASE_URL_ENV: "sqlite+pysqlite:///:memory:",
                            PORT_ENV: value,
                        }
                    )

    def test_invalid_log_level_is_rejected(self) -> None:
        with self.assertRaises(ServerConfigurationError):
            ServerSettings.from_environment(
                {
                    DATABASE_URL_ENV: "sqlite+pysqlite:///:memory:",
                    LOG_LEVEL_ENV: "verbose",
                }
            )

    def test_database_url_is_not_exposed_by_repr(self) -> None:
        secret_url = "mssql+pyodbc://user:secret@example/database"
        settings = ServerSettings(database_url=secret_url)
        self.assertNotIn(secret_url, repr(settings))
        self.assertNotIn("secret", repr(settings))

    def test_run_server_passes_explicit_uvicorn_configuration(self) -> None:
        settings = ServerSettings(
            database_url="sqlite+pysqlite:///:memory:",
            host="0.0.0.0",
            port=8123,
            log_level="debug",
            actor_name="test",
        )
        fake_app = object()
        with (
            patch("app.server.runtime.create_configured_app", return_value=fake_app) as create_app,
            patch("app.server.runtime.uvicorn.run") as uvicorn_run,
        ):
            run_server(settings)

        create_app.assert_called_once_with(settings)
        uvicorn_run.assert_called_once_with(
            fake_app,
            host="0.0.0.0",
            port=8123,
            log_level="debug",
            reload=False,
        )

    def test_main_reports_configuration_error_without_starting_uvicorn(self) -> None:
        with patch(
            "app.server.runtime.run_server",
            side_effect=ServerConfigurationError("base absente"),
        ):
            with self.assertRaises(SystemExit) as caught:
                main()

        self.assertIn("Configuration serveur invalide", str(caught.exception))
        self.assertIn("base absente", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
