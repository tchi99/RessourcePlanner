from __future__ import annotations

from functools import partial

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from app.application.security import AuthPrincipal, ROLE_PROJECT_MANAGER
from app.infrastructure.sql import (
    Base,
    Project,
    create_session_factory,
    create_sql_engine,
)
from app.server import create_api_app


def project_manager_resolver(_request):
    return AuthPrincipal.from_roles(
        local_user_id="PM-TEST",
        issuer="urn:resourceplanner:test",
        subject="pm-test",
        display_name="Chargé test",
        email=None,
        roles=(ROLE_PROJECT_MANAGER,),
        auth_mode="test",
    )


from tests.http_test_auth import TEST_ADMIN_AUTH_RESOLVER

create_api_app = partial(create_api_app, auth_resolver=TEST_ADMIN_AUTH_RESOLVER)

class CompetencyCatalogApiTests(unittest.TestCase):
    def _database_url(self, directory: str) -> str:
        database = Path(directory) / "competencies.db"
        database_url = f"sqlite+pysqlite:///{database.as_posix()}"
        engine = create_sql_engine(database_url)
        Base.metadata.create_all(engine)
        factory = create_session_factory(engine)
        with factory.begin() as session:
            session.add(
                Project(
                    id="PROJECT-272",
                    number="P-272",
                    name="Projet compétences",
                    status="Actif",
                )
            )
        engine.dispose()
        return database_url

    def test_catalog_assignments_and_compatibility_snapshots(self) -> None:
        with TemporaryDirectory() as directory:
            database_url = self._database_url(directory)
            app = create_api_app(database_url)
            with TestClient(app) as client:
                scada = client.post(
                    "/api/v1/competencies",
                    json={
                        "name": "SCADA",
                        "description": "Supervision",
                        "sort_order": 10,
                    },
                )
                self.assertEqual(scada.status_code, 201)
                scada_id = scada.json()["competency_id"]

                plc = client.post(
                    "/api/v1/competencies",
                    json={
                        "name": "PLC",
                        "description": "Automates",
                        "sort_order": 20,
                    },
                )
                self.assertEqual(plc.status_code, 201)
                plc_id = plc.json()["competency_id"]

                duplicate = client.post(
                    "/api/v1/competencies",
                    json={"name": "scada"},
                )
                self.assertEqual(duplicate.status_code, 409)
                self.assertEqual(
                    duplicate.json()["error"]["code"],
                    "competency_name_conflict",
                )

                created_resource = client.post(
                    "/api/v1/resources",
                    headers={"Idempotency-Key": "competency-resource-1"},
                    json={
                        "name": "Technicien compétences",
                        "competencies": "ancienne valeur ignorée",
                        "competency_ids": [scada_id, plc_id],
                        "active": True,
                        "sort_order": 10,
                    },
                )
                self.assertEqual(created_resource.status_code, 201)
                resource_id = created_resource.json()["resource_id"]

                resources = client.get(
                    "/api/v1/resources",
                    params={"active_only": "false"},
                )
                self.assertEqual(resources.status_code, 200)
                resource = next(
                    row for row in resources.json() if row["id"] == resource_id
                )
                self.assertEqual(
                    set(resource["competency_ids"]),
                    {scada_id, plc_id},
                )
                self.assertEqual(resource["competencies"], "SCADA; PLC")

                created_demand = client.post(
                    "/api/v1/demands",
                    headers={"Idempotency-Key": "competency-demand-1"},
                    json={
                        "project_number": "P-272",
                        "desired_start": "2026-09-21",
                        "desired_end": "2026-09-22",
                        "description": "Besoin SCADA",
                        "estimated_hours": 8,
                        "required_competency_ids": [scada_id],
                    },
                )
                self.assertEqual(created_demand.status_code, 201)
                demand_number = created_demand.json()["demand_number"]

                demand = client.get(f"/api/v1/demands/{demand_number}")
                self.assertEqual(demand.status_code, 200)
                self.assertEqual(demand.json()["required_competency_ids"], [scada_id])
                self.assertEqual(demand.json()["required_competencies"], "SCADA")

                created_segment = client.post(
                    "/api/v1/segments",
                    headers={"Idempotency-Key": "competency-segment-1"},
                    json={
                        "demand_number": demand_number,
                        "start_date": "2026-09-21",
                        "end_date": "2026-09-21",
                        "planned_hours": 8,
                        "description": "Besoin ciblé",
                        "required_competency_id": scada_id,
                    },
                )
                self.assertEqual(created_segment.status_code, 201)
                segment_id = created_segment.json()["segment_id"]
                segment = client.get(f"/api/v1/segments/{segment_id}")
                self.assertEqual(segment.status_code, 200)
                self.assertEqual(segment.json()["required_competency_id"], scada_id)
                self.assertEqual(segment.json()["required_competency"], "SCADA")

                renamed = client.patch(
                    f"/api/v1/competencies/{scada_id}",
                    json={"name": "SCADA / HMI"},
                )
                self.assertEqual(renamed.status_code, 200)

                resource = next(
                    row
                    for row in client.get(
                        "/api/v1/resources",
                        params={"active_only": "false"},
                    ).json()
                    if row["id"] == resource_id
                )
                self.assertEqual(resource["competencies"], "SCADA / HMI; PLC")
                self.assertEqual(
                    client.get(f"/api/v1/demands/{demand_number}").json()[
                        "required_competencies"
                    ],
                    "SCADA / HMI",
                )
                self.assertEqual(
                    client.get(f"/api/v1/segments/{segment_id}").json()[
                        "required_competency"
                    ],
                    "SCADA / HMI",
                )

                deactivated = client.post(
                    f"/api/v1/competencies/{scada_id}/deactivate"
                )
                self.assertEqual(deactivated.status_code, 200)
                all_rows = client.get(
                    "/api/v1/competencies",
                    params={"active_only": "false"},
                ).json()
                self.assertFalse(
                    next(row for row in all_rows if row["id"] == scada_id)["active"]
                )

                rejected = client.post(
                    "/api/v1/resources",
                    headers={"Idempotency-Key": "competency-resource-inactive"},
                    json={
                        "name": "Ressource invalide",
                        "competency_ids": [scada_id],
                    },
                )
                self.assertEqual(rejected.status_code, 422)
                self.assertEqual(
                    rejected.json()["error"]["code"],
                    "competency_inactive",
                )

    def test_catalog_mutations_require_resource_admin_permission(self) -> None:
        with TemporaryDirectory() as directory:
            database_url = self._database_url(directory)
            app = create_api_app(
                database_url,
                auth_resolver=project_manager_resolver,
            )
            with TestClient(app) as client:
                read = client.get("/api/v1/competencies")
                self.assertEqual(read.status_code, 200)

                write = client.post(
                    "/api/v1/competencies",
                    json={"name": "SCADA"},
                )
                self.assertEqual(write.status_code, 403)
                self.assertEqual(
                    write.json()["error"]["context"]["required_permission"],
                    "manage_resources",
                )


if __name__ == "__main__":
    unittest.main()
