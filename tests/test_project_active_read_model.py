from __future__ import annotations

from functools import partial

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from app.infrastructure.sql import Base, Project, create_session_factory, create_sql_engine, transactional_session
from app.server import create_api_app


from tests.http_test_auth import TEST_ADMIN_AUTH_RESOLVER

create_api_app = partial(create_api_app, auth_resolver=TEST_ADMIN_AUTH_RESOLVER)

class ProjectActiveReadModelTests(unittest.TestCase):
    def _database(self, directory: str) -> str:
        path = Path(directory) / "projects.db"
        url = f"sqlite:///{path.as_posix()}"
        engine = create_sql_engine(url)
        Base.metadata.create_all(engine)
        factory = create_session_factory(engine)
        with transactional_session(factory) as session:
            session.add_all(
                [
                    Project(id="P1", number="P-1", name="Actif", status="Actif"),
                    Project(id="P2", number="P-2", name="Terminé", status="Terminé"),
                    Project(id="P3", number="P-3", name="Annulé", status="Annulé"),
                ]
            )
        engine.dispose()
        return url

    def test_project_read_model_exposes_active_without_frontend_status_rules(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(self._database(directory))
            with TestClient(app) as client:
                all_projects = client.get("/api/v1/projects?active_only=false")
                active_projects = client.get("/api/v1/projects?active_only=true")

            self.assertEqual(all_projects.status_code, 200)
            rows = {row["number"]: row for row in all_projects.json()}
            self.assertTrue(rows["P-1"]["active"])
            self.assertFalse(rows["P-2"]["active"])
            self.assertFalse(rows["P-3"]["active"])
            self.assertEqual([row["number"] for row in active_projects.json()], ["P-1"])


if __name__ == "__main__":
    unittest.main()
