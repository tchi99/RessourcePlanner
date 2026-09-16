from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from app.infrastructure.sql import Base, create_sql_engine
from app.infrastructure.sql.models import Project, WorkforceRequest, WorkforceRequestHistory
from app.server import create_api_app


class ServerDemandHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        path = Path(self.temp.name) / "history.db"
        self.database_url = f"sqlite+pysqlite:///{path.as_posix()}"
        engine = create_sql_engine(self.database_url)
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(
                Project.__table__.insert().values(
                    id="P1",
                    number="P-1",
                    name="Projet",
                    status="Actif",
                )
            )
            connection.execute(
                WorkforceRequest.__table__.insert().values(
                    id="WR1",
                    legacy_demand_number="DMO-2026-0001",
                    project_id="P1",
                    status="Soumise",
                    resource_count=1,
                )
            )
            connection.execute(
                WorkforceRequestHistory.__table__.insert().values(
                    id="H1",
                    workforce_request_id="WR1",
                    action="Soumission",
                    previous_status="Brouillon",
                    status="Soumise",
                    comment="Prête pour approbation",
                    actor_name="Coordonnateur",
                    occurred_at=datetime(2026, 9, 16, 13, 0, tzinfo=timezone.utc),
                )
            )
        engine.dispose()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_history_endpoint_returns_typed_business_event(self) -> None:
        app = create_api_app(self.database_url)
        with TestClient(app) as client:
            response = client.get("/api/v1/demands/DMO-2026-0001/history")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["demand_number"], "DMO-2026-0001")
        self.assertEqual(payload[0]["action"], "Soumission")
        self.assertEqual(payload[0]["previous_status"], "Brouillon")
        self.assertEqual(payload[0]["status"], "Soumise")
        self.assertEqual(payload[0]["actor_name"], "Coordonnateur")
        self.assertIn("2026-09-16", payload[0]["occurred_at"])
        self.assertNotIn("workforce_request_id", payload[0])
        self.assertNotIn("actor_external_id", payload[0])

    def test_unknown_demand_returns_standard_not_found_contract(self) -> None:
        app = create_api_app(self.database_url)
        with TestClient(app) as client:
            response = client.get("/api/v1/demands/UNKNOWN/history")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "demand_not_found")


if __name__ == "__main__":
    unittest.main()
