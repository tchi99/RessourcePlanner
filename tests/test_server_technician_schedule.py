from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from app.application.security import AuthPrincipal, ROLE_TECHNICIAN
from app.infrastructure.sql import Base, Resource, create_sql_engine
from app.server import create_api_app
from app.server.security import static_auth_resolver


class ServerTechnicianScheduleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        path = Path(self.temp.name) / "technician.db"
        self.database_url = f"sqlite+pysqlite:///{path.as_posix()}"
        engine = create_sql_engine(self.database_url)
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(
                Resource.__table__.insert().values(
                    id="R-TECH",
                    external_id="EMP-TECH",
                    name="Technicien lié",
                    active=True,
                    sort_order=0,
                )
            )
        engine.dispose()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _app(self, employee_external_id: str | None):
        principal = AuthPrincipal.from_roles(
            local_user_id="U-TECH",
            issuer="issuer",
            subject="subject",
            display_name="Technicien test",
            email=None,
            employee_external_id=employee_external_id,
            roles=(ROLE_TECHNICIAN,),
            auth_mode="test",
        )
        return create_api_app(
            self.database_url,
            auth_resolver=static_auth_resolver(principal),
        )

    def test_technician_can_read_linked_personal_schedule(self) -> None:
        app = self._app("EMP-TECH")
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/me/schedule?start=2026-09-16&end=2026-09-20"
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["link_status"], "LINKED")
        self.assertEqual(payload["employee_external_id"], "EMP-TECH")
        self.assertEqual(payload["resource"]["id"], "R-TECH")
        self.assertEqual(payload["shifts"], [])

    def test_unlinked_technician_gets_non_error_state(self) -> None:
        app = self._app(None)
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/me/schedule?start=2026-09-16&end=2026-09-16"
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["link_status"], "UNLINKED")
        self.assertIsNone(payload["resource"])

    def test_invalid_window_returns_structured_validation_error(self) -> None:
        app = self._app("EMP-TECH")
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/me/schedule?start=2026-09-20&end=2026-09-16"
            )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["error"]["code"],
            "technician_schedule_date_window_invalid",
        )


if __name__ == "__main__":
    unittest.main()
