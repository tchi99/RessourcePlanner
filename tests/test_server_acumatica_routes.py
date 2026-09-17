from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from app.application import ExternalProjectRecord
from app.infrastructure.sql import Base, create_sql_engine
from app.performance_diagnostics import read_performance_samples
from app.server import create_api_app


class StubProjectSource:
    def __init__(self) -> None:
        self.rows = [
            ExternalProjectRecord(
                external_id="ERP-1",
                number="P-100",
                name="Projet Acumatica",
                client="Client A",
                project_manager_name="Alice",
                status="Active",
            )
        ]

    def list_projects(self):
        return tuple(self.rows)


class ServerAcumaticaRouteTests(unittest.TestCase):
    def _database(self, directory: str) -> str:
        path = Path(directory) / "acumatica.db"
        url = f"sqlite:///{path.as_posix()}"
        engine = create_sql_engine(url)
        Base.metadata.create_all(engine)
        engine.dispose()
        return url

    def test_unconfigured_integration_reports_status_and_returns_503_for_sync(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(self._database(directory))
            with TestClient(app) as client:
                status = client.get("/api/v1/integrations/acumatica")
                sync = client.post("/api/v1/integrations/acumatica/projects/sync")

            self.assertEqual(status.status_code, 200)
            self.assertEqual(status.json(), {"configured": False})
            self.assertEqual(sync.status_code, 503)
            self.assertEqual(sync.json()["error"]["code"], "acumatica_not_configured")

    def test_configured_sync_persists_projects_and_is_idempotent(self) -> None:
        with TemporaryDirectory() as directory:
            source = StubProjectSource()
            performance_log = Path(directory) / "performance.jsonl"
            app = create_api_app(
                self._database(directory),
                project_source=source,
                acumatica_info={
                    "endpoint": "Default",
                    "version": "25.200.001",
                    "entity": "Project",
                },
                performance_log_path=performance_log,
            )
            with TestClient(app) as client:
                status = client.get("/api/v1/integrations/acumatica")
                first = client.post("/api/v1/integrations/acumatica/projects/sync")
                second = client.post("/api/v1/integrations/acumatica/projects/sync")
                projects = client.get("/api/v1/projects")

            self.assertEqual(status.status_code, 200)
            self.assertEqual(
                status.json(),
                {
                    "configured": True,
                    "endpoint": "Default",
                    "version": "25.200.001",
                    "entity": "Project",
                },
            )
            self.assertEqual(first.status_code, 200)
            self.assertEqual(
                first.json(),
                {"received": 1, "created": 1, "updated": 0, "unchanged": 0},
            )
            self.assertEqual(
                second.json(),
                {"received": 1, "created": 0, "updated": 0, "unchanged": 1},
            )
            self.assertEqual(projects.status_code, 200)
            self.assertEqual(projects.json()[0]["number"], "P-100")
            self.assertEqual(projects.json()[0]["erp_external_id"], "ERP-1")
            self.assertEqual(projects.json()[0]["project_manager"], "Alice")

            samples = read_performance_samples(path=performance_log, limit=20)
            sync_samples = [
                sample
                for sample in samples
                if sample.get("operation")
                == "http POST /api/v1/integrations/acumatica/projects/sync"
            ]
            self.assertEqual(len(sync_samples), 2)
            for sample in sync_samples:
                self.assertEqual(sample["external_call_count"], 1)
                self.assertEqual(sample["external_item_count"], 1)
                self.assertGreater(sample["db_query_count"], 0)
                self.assertGreaterEqual(sample["external_seconds"], 0.0)
                self.assertGreaterEqual(sample["compute_seconds"], 0.0)


if __name__ == "__main__":
    unittest.main()
