from __future__ import annotations

from functools import partial

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.application import ApplicationOperationError
from app.infrastructure.sql import Base, create_sql_engine
from app.server import create_api_app
from app.server.readiness import expected_alembic_head
from app.server.security import static_auth_resolver


from tests.http_test_auth import TEST_ADMIN_AUTH_RESOLVER

create_api_app = partial(create_api_app, auth_resolver=TEST_ADMIN_AUTH_RESOLVER)

class FailingExternalProjectSource:
    def list_projects(self):
        raise ApplicationOperationError(
            "Source externe indisponible.",
            code="external_unavailable",
        )


class RuntimeReadinessTests(unittest.TestCase):
    def _database(self, directory: str, *, revision: str | None = None) -> str:
        path = Path(directory) / "runtime-ready.db"
        url = f"sqlite:///{path.as_posix()}"
        engine = create_sql_engine(url)
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE alembic_version "
                    "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
                )
            )
            connection.execute(
                text("INSERT INTO alembic_version(version_num) VALUES (:revision)"),
                {"revision": revision or expected_alembic_head()},
            )
        engine.dispose()
        return url

    def test_health_is_liveness_even_when_database_is_not_migrated(self) -> None:
        app = create_api_app("sqlite+pysqlite:///:memory:")

        with TestClient(app) as client:
            health = client.get("/health")
            ready = client.get("/ready")

        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json(), {"status": "ok", "api": "v1"})
        self.assertEqual(ready.status_code, 503)
        self.assertEqual(ready.json()["status"], "not_ready")
        self.assertEqual(ready.json()["database"]["reason"], "migration_missing")

    def test_readiness_requires_exact_alembic_head(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(self._database(directory, revision="outdated_revision"))
            with TestClient(app) as client:
                ready = client.get("/ready")

        self.assertEqual(ready.status_code, 503)
        self.assertEqual(ready.json()["database"]["reason"], "migration_required")
        self.assertNotIn("outdated_revision", ready.text)

    def test_ready_reports_only_safe_external_dependency_configuration(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(
                self._database(directory),
                runtime_dependencies={
                    "oidc": {
                        "required": False,
                        "configured": False,
                        "check": "configuration_only",
                    },
                    "acumatica": {
                        "required": False,
                        "configured": True,
                        "check": "configuration_only",
                    },
                    "m365": {
                        "required": False,
                        "configured": True,
                        "check": "configuration_only",
                    },
                },
            )
            with TestClient(app) as client:
                ready = client.get("/ready")

        self.assertEqual(ready.status_code, 200)
        payload = ready.json()
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["database"]["status"], "ok")
        self.assertEqual(payload["database"]["alembic_revision"], expected_alembic_head())
        self.assertTrue(payload["external_dependencies"]["acumatica"]["configured"])
        self.assertTrue(payload["external_dependencies"]["m365"]["configured"])
        self.assertNotIn("token", ready.text.casefold())
        self.assertNotIn("mailbox", ready.text.casefold())
        self.assertNotIn("url", ready.text.casefold())

    def test_external_outage_does_not_block_local_reads_or_readiness(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(
                self._database(directory),
                project_source=FailingExternalProjectSource(),
                runtime_dependencies={
                    "acumatica": {
                        "required": False,
                        "configured": True,
                        "check": "configuration_only",
                    }
                },
            )
            with TestClient(app) as client:
                ready = client.get("/ready")
                projects = client.get("/api/v1/projects")

        self.assertEqual(ready.status_code, 200)
        self.assertEqual(projects.status_code, 200)
        self.assertEqual(projects.json(), [])

    def test_health_and_readiness_are_public_even_when_authentication_fails(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(
                self._database(directory),
                auth_resolver=static_auth_resolver(None),
            )
            with TestClient(app) as client:
                health = client.get("/health")
                ready = client.get("/ready")
                projects = client.get("/api/v1/projects")

        self.assertEqual(health.status_code, 200)
        self.assertEqual(ready.status_code, 200)
        self.assertEqual(projects.status_code, 401)


if __name__ == "__main__":
    unittest.main()
