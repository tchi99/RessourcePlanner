from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from app.infrastructure.sql import (
    Base,
    Project,
    TaskCatalogEntry,
    create_session_factory,
    create_sql_engine,
)
from app.server import create_api_app


class TaskCatalogApiTests(unittest.TestCase):
    def test_search_and_demand_selection_use_project_scoped_task_code(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "task-api.db"
            database_url = f"sqlite+pysqlite:///{database.as_posix()}"
            engine = create_sql_engine(database_url)
            Base.metadata.create_all(engine)
            factory = create_session_factory(engine)
            with factory.begin() as session:
                session.add_all(
                    [
                        Project(
                            id="PROJECT-1",
                            number="P-1",
                            name="Projet 1",
                            status="Actif",
                        ),
                        Project(
                            id="PROJECT-2",
                            number="P-2",
                            name="Projet 2",
                            status="Actif",
                        ),
                        TaskCatalogEntry(
                            id="TASK-P1-210",
                            project_number="P-1",
                            task_code="210",
                            label="AUTOMATISATION",
                            status="Actif",
                            active=True,
                            time_entry_enabled=True,
                        ),
                        TaskCatalogEntry(
                            id="TASK-P2-210",
                            project_number="P-2",
                            task_code="210",
                            label="ACHATS AUTOMATISATION",
                            status="Actif",
                            active=True,
                        ),
                    ]
                )
            engine.dispose()

            app = create_api_app(database_url)
            with TestClient(app) as client:
                response = client.get(
                    "/api/v1/task-catalog",
                    params={"project_number": "P-1", "q": "auto"},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(response.json()), 1)
                self.assertEqual(response.json()[0]["code"], "210")
                self.assertEqual(response.json()[0]["label"], "AUTOMATISATION")

                created = client.post(
                    "/api/v1/demands",
                    headers={"Idempotency-Key": "task-catalog-demand-1"},
                    json={
                        "project_number": "P-1",
                        "desired_start": "2026-09-21",
                        "task_code": "210",
                        "description": "Test tâche ERP",
                    },
                )
                self.assertEqual(created.status_code, 201)
                number = created.json()["demand_number"]

                detail = client.get(f"/api/v1/demands/{number}")
                self.assertEqual(detail.status_code, 200)
                self.assertEqual(detail.json()["task_code"], "210")
                self.assertEqual(detail.json()["task_label"], "AUTOMATISATION")

                wrong_project = client.post(
                    "/api/v1/demands",
                    headers={"Idempotency-Key": "task-catalog-demand-2"},
                    json={
                        "project_number": "P-1",
                        "desired_start": "2026-09-21",
                        "task_code": "999",
                    },
                )
                self.assertGreaterEqual(wrong_project.status_code, 400)


if __name__ == "__main__":
    unittest.main()
