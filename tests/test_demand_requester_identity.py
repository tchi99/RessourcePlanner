from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.application.security import (
    AuthPrincipal,
    ROLE_COORDINATOR,
    ROLE_PROJECT_MANAGER,
    ROLE_TECHNICIAN,
)
from app.infrastructure.sql import (
    Base,
    Project,
    SqlUserIdentityRepository,
    WorkforceRequest,
    WorkforceRequestHistory,
    create_session_factory,
    create_sql_engine,
)
from app.server import create_api_app
from app.server.security import static_auth_resolver


class DemandRequesterIdentityTests(unittest.TestCase):
    @staticmethod
    def _principal(
        user_id: str,
        display_name: str,
        roles: tuple[str, ...],
    ):
        return static_auth_resolver(
            AuthPrincipal.from_roles(
                local_user_id=user_id,
                issuer="urn:test:requesters",
                subject=f"subject:{user_id}",
                display_name=display_name,
                email=None,
                roles=roles,
                auth_mode="test",
            )
        )

    @staticmethod
    def _database(directory: str) -> tuple[str, dict[str, str]]:
        path = Path(directory) / "requesters.db"
        url = f"sqlite+pysqlite:///{path.as_posix()}"
        engine = create_sql_engine(url)
        Base.metadata.create_all(engine)
        factory = create_session_factory(engine)
        with factory.begin() as session:
            session.add(Project(id="P1", number="P-1", name="Projet identité"))
            identities = SqlUserIdentityRepository(session)
            users = {
                "pm1": identities.upsert(
                    issuer="urn:test",
                    subject="pm1",
                    display_name="PM Un",
                    email=None,
                    roles=(ROLE_PROJECT_MANAGER,),
                ).user_id,
                "pm2": identities.upsert(
                    issuer="urn:test",
                    subject="pm2",
                    display_name="PM Deux",
                    email=None,
                    roles=(ROLE_PROJECT_MANAGER,),
                ).user_id,
                "coord": identities.upsert(
                    issuer="urn:test",
                    subject="coord",
                    display_name="Coordonnateur",
                    email=None,
                    roles=(ROLE_COORDINATOR,),
                ).user_id,
                "tech": identities.upsert(
                    issuer="urn:test",
                    subject="tech",
                    display_name="Technicien",
                    email=None,
                    roles=(ROLE_TECHNICIAN,),
                ).user_id,
            }
        engine.dispose()
        return url, users

    def test_project_manager_cannot_impersonate_requester_by_direct_api(self) -> None:
        with TemporaryDirectory() as directory:
            database_url, users = self._database(directory)
            app = create_api_app(
                database_url,
                auth_resolver=self._principal(
                    users["pm1"],
                    "PM Un",
                    (ROLE_PROJECT_MANAGER,),
                ),
            )
            with TestClient(app, raise_server_exceptions=False) as client:
                forbidden = client.post(
                    "/api/v1/demands",
                    json={
                        "project_number": "P-1",
                        "desired_start": "2026-09-22",
                        "requester_user_id": users["pm2"],
                    },
                )
                self.assertEqual(forbidden.status_code, 403, forbidden.text)
                self.assertEqual(
                    forbidden.json()["error"]["code"],
                    "demand_requester_impersonation_forbidden",
                )

                created = client.post(
                    "/api/v1/demands",
                    json={
                        "project_number": "P-1",
                        "desired_start": "2026-09-22",
                    },
                )
                self.assertEqual(created.status_code, 201, created.text)
                number = created.json()["demand_number"]

                detail = client.get(f"/api/v1/demands/{number}")
                self.assertEqual(detail.status_code, 200, detail.text)
                self.assertEqual(detail.json()["requester_user_id"], users["pm1"])
                self.assertEqual(detail.json()["requester"], "PM Un")

                forbidden_update = client.patch(
                    f"/api/v1/demands/{number}",
                    json={"requester_user_id": users["pm2"]},
                )
                self.assertEqual(
                    forbidden_update.status_code,
                    403,
                    forbidden_update.text,
                )
                self.assertEqual(
                    forbidden_update.json()["error"]["code"],
                    "demand_requester_impersonation_forbidden",
                )

    def test_coordinator_delegation_keeps_actor_and_requester_distinct(self) -> None:
        with TemporaryDirectory() as directory:
            database_url, users = self._database(directory)
            app = create_api_app(
                database_url,
                auth_resolver=self._principal(
                    users["coord"],
                    "Coordonnateur",
                    (ROLE_COORDINATOR,),
                ),
            )
            with TestClient(app, raise_server_exceptions=False) as client:
                requester_list = client.get("/api/v1/demand-requesters")
                self.assertEqual(requester_list.status_code, 200, requester_list.text)
                listed_ids = {row["user_id"] for row in requester_list.json()}
                self.assertIn(users["pm1"], listed_ids)
                self.assertIn(users["pm2"], listed_ids)
                self.assertIn(users["coord"], listed_ids)
                self.assertNotIn(users["tech"], listed_ids)

                created = client.post(
                    "/api/v1/demands",
                    json={
                        "project_number": "P-1",
                        "desired_start": "2026-09-22",
                        "requester_user_id": users["pm2"],
                    },
                )
                self.assertEqual(created.status_code, 201, created.text)
                number = created.json()["demand_number"]

                history = client.get(f"/api/v1/demands/{number}/history")
                self.assertEqual(history.status_code, 200, history.text)
                self.assertEqual(history.json()[0]["actor_user_id"], users["coord"])

            engine = create_sql_engine(database_url)
            factory = create_session_factory(engine)
            try:
                with factory() as session:
                    request = session.scalar(
                        select(WorkforceRequest).where(
                            WorkforceRequest.legacy_demand_number == number
                        )
                    )
                    assert request is not None
                    self.assertEqual(request.requester_user_id, users["pm2"])
                    self.assertEqual(request.requester_name, "PM Deux")
                    event = session.scalar(
                        select(WorkforceRequestHistory).where(
                            WorkforceRequestHistory.workforce_request_id == request.id
                        )
                    )
                    assert event is not None
                    self.assertEqual(event.actor_user_id, users["coord"])
                    self.assertNotEqual(event.actor_user_id, request.requester_user_id)
            finally:
                engine.dispose()

    def test_multi_role_coordinator_may_delegate_and_technician_cannot_list(self) -> None:
        with TemporaryDirectory() as directory:
            database_url, users = self._database(directory)
            multi_role_app = create_api_app(
                database_url,
                auth_resolver=self._principal(
                    users["coord"],
                    "Coordonnateur",
                    (ROLE_PROJECT_MANAGER, ROLE_COORDINATOR),
                ),
            )
            with TestClient(multi_role_app, raise_server_exceptions=False) as client:
                delegated = client.post(
                    "/api/v1/demands",
                    json={
                        "project_number": "P-1",
                        "desired_start": "2026-09-22",
                        "requester_user_id": users["pm1"],
                    },
                )
                self.assertEqual(delegated.status_code, 201, delegated.text)

            technician_app = create_api_app(
                database_url,
                auth_resolver=self._principal(
                    users["tech"],
                    "Technicien",
                    (ROLE_TECHNICIAN,),
                ),
            )
            with TestClient(technician_app, raise_server_exceptions=False) as client:
                forbidden = client.get("/api/v1/demand-requesters")
                self.assertEqual(forbidden.status_code, 403, forbidden.text)


if __name__ == "__main__":
    unittest.main()
