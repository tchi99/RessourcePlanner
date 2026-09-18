from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.application import ApplicationOperationError, ExternalProjectRecord
from app.infrastructure.sql import (
    Base,
    Project,
    create_session_factory,
    create_sql_engine,
    transactional_session,
)
from app.performance_diagnostics import read_performance_samples
from app.server import create_api_app


class StubProjectSource:
    def __init__(self, rows: list[ExternalProjectRecord] | None = None) -> None:
        self.rows = rows or [
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


class FailingProjectSource:
    def list_projects(self):
        raise ApplicationOperationError(
            "Impossible de lire les projets depuis Acumatica.",
            code="acumatica_project_read_failed",
            context={
                "failure_kind": "timeout",
                "retryable": True,
                "endpoint": "Default",
                "entity": "Project",
            },
        )


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

    def test_failed_external_read_keeps_external_metrics_coherent(self) -> None:
        with TemporaryDirectory() as directory:
            performance_log = Path(directory) / "performance.jsonl"
            app = create_api_app(
                self._database(directory),
                project_source=FailingProjectSource(),
                performance_log_path=performance_log,
            )
            with TestClient(app) as client:
                response = client.post("/api/v1/integrations/acumatica/projects/sync")

            self.assertEqual(response.status_code, 500)
            self.assertEqual(response.json()["error"]["code"], "acumatica_project_read_failed")
            self.assertEqual(
                response.json()["error"]["context"]["failure_kind"],
                "timeout",
            )

            samples = read_performance_samples(path=performance_log, limit=10)
            sample = next(
                item
                for item in samples
                if item.get("operation")
                == "http POST /api/v1/integrations/acumatica/projects/sync"
            )
            self.assertEqual(sample["status"], "500")
            self.assertEqual(sample["external_call_count"], 1)
            self.assertEqual(sample["external_item_count"], 0)
            self.assertGreaterEqual(sample["external_seconds"], 0.0)

    def test_mid_sync_conflict_rolls_back_every_project_written_by_that_pull(self) -> None:
        with TemporaryDirectory() as directory:
            database_url = self._database(directory)
            engine = create_sql_engine(database_url)
            factory = create_session_factory(engine)
            try:
                with transactional_session(factory) as session:
                    session.add(
                        Project(
                            id="EXISTING",
                            erp_external_id="ERP-OLD",
                            number="P-CONFLICT",
                            name="Projet existant",
                            status="Active",
                        )
                    )
            finally:
                engine.dispose()

            source = StubProjectSource(
                [
                    ExternalProjectRecord(
                        external_id="ERP-FIRST",
                        number="P-FIRST",
                        name="Devrait être rollback",
                    ),
                    ExternalProjectRecord(
                        external_id="ERP-NEW",
                        number="P-CONFLICT",
                        name="Conflit",
                    ),
                ]
            )
            app = create_api_app(database_url, project_source=source)
            with TestClient(app) as client:
                sync = client.post("/api/v1/integrations/acumatica/projects/sync")
                projects = client.get("/api/v1/projects")

            self.assertEqual(sync.status_code, 409)
            self.assertEqual(
                sync.json()["error"]["code"],
                "project_sync_external_id_conflict",
            )
            numbers = {row["number"] for row in projects.json()}
            self.assertEqual(numbers, {"P-CONFLICT"})
            self.assertNotIn("P-FIRST", numbers)

            verification_engine = create_sql_engine(database_url)
            verification_factory = create_session_factory(verification_engine)
            try:
                with verification_factory() as session:
                    rows = session.scalars(select(Project)).all()
                    self.assertEqual(len(rows), 1)
                    self.assertEqual(rows[0].erp_external_id, "ERP-OLD")
            finally:
                verification_engine.dispose()


if __name__ == "__main__":
    unittest.main()
