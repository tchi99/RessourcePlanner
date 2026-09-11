from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from app.infrastructure.sql import (
    Base,
    Project,
    WorkPackage,
    create_session_factory,
    create_sql_engine,
    transactional_session,
)
from app.server import create_api_app


class ServerWorkPackageRouteTests(unittest.TestCase):
    def _database(self, directory: str) -> str:
        path = Path(directory) / "work-packages.db"
        url = f"sqlite:///{path.as_posix()}"
        engine = create_sql_engine(url)
        Base.metadata.create_all(engine)
        factory = create_session_factory(engine)
        with transactional_session(factory) as session:
            session.add_all(
                [
                    Project(id="P1", number="P-1", name="Projet 1", status="Actif"),
                    Project(id="P2", number="P-2", name="Projet 2", status="Actif"),
                ]
            )
            session.flush()
            session.add_all(
                [
                    WorkPackage(
                        id="WP1",
                        project_id="P1",
                        code="DEV",
                        name="Développement",
                        description="Programmation et essais",
                        start_date=date(2026, 9, 14),
                        end_date=date(2026, 9, 25),
                        planned_hours=Decimal("80"),
                        status="planned",
                        legacy_effort_id="EFF-001",
                    ),
                    WorkPackage(
                        id="WP2",
                        project_id="P1",
                        name="Ancienne phase",
                        status="Terminé",
                        legacy_effort_id="EFF-OLD",
                    ),
                    WorkPackage(
                        id="WP3",
                        project_id="P2",
                        name="Installation",
                        status="planned",
                    ),
                ]
            )
        engine.dispose()
        return url

    def test_endpoint_filters_by_project_and_active_status(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(self._database(directory))
            with TestClient(app) as client:
                active = client.get(
                    "/api/v1/work-packages?project_number=P-1&active_only=true"
                )
                all_rows = client.get(
                    "/api/v1/work-packages?project_number=P-1&active_only=false"
                )

            self.assertEqual(active.status_code, 200, active.text)
            self.assertEqual([row["reference"] for row in active.json()], ["EFF-001"])
            self.assertEqual(active.json()[0]["project_number"], "P-1")
            self.assertEqual(active.json()[0]["planned_hours"], 80.0)
            self.assertEqual(active.json()[0]["code"], "DEV")

            self.assertEqual(all_rows.status_code, 200, all_rows.text)
            self.assertEqual(
                {row["reference"] for row in all_rows.json()},
                {"EFF-001", "EFF-OLD"},
            )

    def test_reference_falls_back_to_sql_id_when_no_legacy_effort_exists(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(self._database(directory))
            with TestClient(app) as client:
                response = client.get(
                    "/api/v1/work-packages?project_number=P-2&active_only=true"
                )

            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()[0]["reference"], "WP3")

    def test_openapi_exposes_work_package_read_model(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(self._database(directory))
            with TestClient(app) as client:
                schema = client.get("/openapi.json").json()

            components = schema.get("components", {}).get("schemas", {})
            self.assertIn("WorkPackageReadModel", components)
            self.assertIn("/api/v1/work-packages", schema["paths"])


if __name__ == "__main__":
    unittest.main()
