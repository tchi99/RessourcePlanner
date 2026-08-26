from __future__ import annotations

from contextlib import redirect_stderr
from io import StringIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.infrastructure.sql import (
    Base,
    Project,
    Resource,
    create_session_factory,
    create_sql_engine,
    transactional_session,
)
from app.server.runtime import ServerSettings
from tools.check_server_runtime import (
    ServerReadinessError,
    check_server_runtime,
    main,
)


class ServerReadinessToolTests(unittest.TestCase):
    def _ready_database(self, directory: str) -> str:
        path = Path(directory) / "ready.db"
        url = f"sqlite:///{path.as_posix()}"
        engine = create_sql_engine(url)
        Base.metadata.create_all(engine)
        factory = create_session_factory(engine)
        with transactional_session(factory) as session:
            session.add_all(
                [
                    Project(id="P1", number="P-1", name="Projet actif", status="Actif"),
                    Resource(id="R1", name="Alice", active=True, sort_order=10),
                ]
            )
        engine.dispose()
        return url

    def test_readiness_check_exercises_health_reads_and_openapi(self) -> None:
        with TemporaryDirectory() as directory:
            settings = ServerSettings(database_url=self._ready_database(directory))
            summary = check_server_runtime(settings)

        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["database"], "sqlite")
        self.assertEqual(summary["api"], "v1")
        self.assertEqual(summary["active_projects"], 1)
        self.assertEqual(summary["active_resources"], 1)
        self.assertGreater(summary["openapi_paths"], 1)
        self.assertNotIn("database_url", summary)

    def test_readiness_check_fails_when_schema_is_not_migrated(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "empty.db"
            settings = ServerSettings(database_url=f"sqlite:///{path.as_posix()}")
            with self.assertRaises(ServerReadinessError) as caught:
                check_server_runtime(settings)

        self.assertIn("/api/v1/projects", str(caught.exception))
        self.assertIn("HTTP 500", str(caught.exception))

    def test_cli_returns_configuration_exit_code_without_database_url(self) -> None:
        stderr = StringIO()
        with patch.dict(os.environ, {}, clear=True), redirect_stderr(stderr):
            exit_code = main()

        self.assertEqual(exit_code, 2)
        self.assertIn("configuration_error", stderr.getvalue())
        self.assertIn("RESOURCEPLANNER_DATABASE_URL", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
