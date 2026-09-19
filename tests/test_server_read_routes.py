from __future__ import annotations

from functools import partial

from datetime import date
from decimal import Decimal
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.infrastructure.sql import (
    Base,
    Project,
    Resource,
    ResourceAvailabilityRule,
    ResourceRequirement,
    Shift,
    SqlDemandRepository,
    create_session_factory,
    create_sql_engine,
    transactional_session,
)
from app.infrastructure.sql.models import WorkforceRequest
from app.server import create_api_app


D1 = date(2026, 8, 24)
D2 = date(2026, 8, 25)


from tests.http_test_auth import TEST_ADMIN_AUTH_RESOLVER

create_api_app = partial(create_api_app, auth_resolver=TEST_ADMIN_AUTH_RESOLVER)

class ServerReadRouteTests(unittest.TestCase):
    def _database(self, directory: str) -> str:
        path = Path(directory) / "reads.db"
        url = f"sqlite:///{path.as_posix()}"
        engine = create_sql_engine(url)
        Base.metadata.create_all(engine)
        factory = create_session_factory(engine)
        with transactional_session(factory) as session:
            session.add_all(
                [
                    Project(
                        id="P1",
                        number="P-1",
                        name="Projet actif",
                        client="Client 1",
                        project_manager_name="Jean",
                        status="Actif",
                    ),
                    Project(id="P2", number="P-2", name="Projet fermé", status="Terminé"),
                    Resource(
                        id="R1",
                        name="Alice",
                        resource_class="Programmation",
                        competencies="PLC; SCADA",
                        active=True,
                        sort_order=10,
                    ),
                    Resource(id="R2", name="Bob", active=False, sort_order=20),
                ]
            )
            session.flush()
            session.add(
                ResourceAvailabilityRule(
                    id="SCH-R1",
                    resource_id="R1",
                    availability_type="Horaire standard",
                    start_date=D1,
                    end_date=date(2026, 12, 31),
                    weekdays="Lun,Mar,Mer,Jeu,Ven",
                    active=True,
                )
            )
            number = SqlDemandRepository(session, actor_name="Jean").create(
                {
                    "NumeroProjet": "P-1",
                    "DateDebutSouhaitee": D1,
                    "DateFinSouhaitee": D2,
                    "Description": "Programmation",
                    "NombreRessources": 1,
                }
            )
            request = session.scalar(
                select(WorkforceRequest).where(
                    WorkforceRequest.legacy_demand_number == number
                )
            )
            assert request is not None
            session.add(
                ResourceRequirement(
                    id="REQ1",
                    legacy_segment_id="SEG-1",
                    project_id="P1",
                    workforce_request_id=request.id,
                    assigned_resource_id="R1",
                    start_date=D1,
                    end_date=D2,
                    planned_hours=Decimal("8"),
                    status="Planifié",
                    description="Segment API",
                    planning_type="Flexible",
                    priority="Normale",
                    origin="REQUEST",
                )
            )
            session.flush()
            session.add_all(
                [
                    Shift(
                        id="S1",
                        legacy_allocation_id="MAN-1",
                        resource_requirement_id="REQ1",
                        resource_id="R1",
                        work_date=D1,
                        hours=Decimal("4"),
                        source="MANUAL",
                        locked=True,
                    ),
                    Shift(
                        id="S2",
                        legacy_allocation_id="AUTO-1",
                        resource_requirement_id="REQ1",
                        resource_id="R1",
                        work_date=D2,
                        hours=Decimal("4"),
                        source="AUTO",
                        locked=False,
                    ),
                ]
            )
            self.demand_number = number
        engine.dispose()
        return url

    def test_projects_and_resources_support_active_filters(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(self._database(directory))
            with TestClient(app) as client:
                active_projects = client.get("/api/v1/projects?active_only=true")
                all_projects = client.get("/api/v1/projects")
                active_resources = client.get("/api/v1/resources")
                all_resources = client.get("/api/v1/resources?active_only=false")

            self.assertEqual(active_projects.status_code, 200)
            self.assertEqual([row["number"] for row in active_projects.json()], ["P-1"])
            self.assertEqual(len(all_projects.json()), 2)
            self.assertEqual([row["name"] for row in active_resources.json()], ["Alice"])
            self.assertEqual(len(all_resources.json()), 2)

    def test_demands_segments_and_shifts_are_canonical_and_filterable(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(self._database(directory))
            with TestClient(app) as client:
                demands = client.get("/api/v1/demands")
                demand = client.get(f"/api/v1/demands/{self.demand_number}")
                segments = client.get(
                    "/api/v1/segments?start=2026-08-25&end=2026-08-25"
                )
                shifts = client.get(
                    "/api/v1/shifts?start=2026-08-24&end=2026-08-24&resource_name=Alice"
                )

            self.assertEqual(demands.status_code, 200)
            self.assertEqual(demands.json()[0]["number"], self.demand_number)
            self.assertEqual(demand.json()["project_number"], "P-1")
            self.assertEqual(segments.status_code, 200)
            self.assertEqual(segments.json()[0]["segment_id"], "SEG-1")
            self.assertEqual(shifts.status_code, 200)
            self.assertEqual(shifts.json()[0]["allocation_id"], "MAN-1")
            self.assertEqual(shifts.json()[0]["segment_id"], "SEG-1")
            self.assertTrue(shifts.json()[0]["locked"])

            serialized = json.dumps(
                {
                    "demand": demand.json(),
                    "segment": segments.json()[0],
                    "shift": shifts.json()[0],
                },
                ensure_ascii=False,
            )
            for legacy in (
                "NumeroProjet",
                "NoDemande",
                "IDSegment",
                "IDAllocation",
                "Technicien",
                "HeuresPrevues",
            ):
                self.assertNotIn(legacy, serialized)

    def test_planning_snapshot_is_atomic_canonical_frontend_payload(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(self._database(directory))
            with TestClient(app) as client:
                response = client.get(
                    "/api/v1/planning/snapshot?start=2026-08-24&end=2026-08-24"
                )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["start"], "2026-08-24")
            self.assertEqual(payload["end"], "2026-08-24")
            self.assertEqual([row["name"] for row in payload["resources"]], ["Alice"])
            self.assertEqual(
                [row["number"] for row in payload["demands"]],
                [self.demand_number],
            )
            self.assertEqual([row["segment_id"] for row in payload["segments"]], ["SEG-1"])
            self.assertEqual([row["allocation_id"] for row in payload["shifts"]], ["MAN-1"])

            serialized = json.dumps(payload, ensure_ascii=False)
            for legacy in ("NoDemande", "IDSegment", "IDAllocation", "Technicien"):
                self.assertNotIn(legacy, serialized)

    def test_missing_entity_and_invalid_window_use_application_error_contract(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(self._database(directory))
            with TestClient(app, raise_server_exceptions=False) as client:
                missing = client.get("/api/v1/demands/DMO-UNKNOWN")
                invalid = client.get(
                    "/api/v1/segments?start=2026-08-25&end=2026-08-24"
                )
                invalid_snapshot = client.get(
                    "/api/v1/planning/snapshot?start=2026-08-25&end=2026-08-24"
                )

            self.assertEqual(missing.status_code, 404)
            self.assertEqual(missing.json()["error"]["code"], "demand_not_found")
            self.assertEqual(invalid.status_code, 422)
            self.assertEqual(
                invalid.json()["error"]["code"],
                "query_date_window_invalid",
            )
            self.assertEqual(invalid_snapshot.status_code, 422)
            self.assertEqual(
                invalid_snapshot.json()["error"]["code"],
                "query_date_window_invalid",
            )

    def test_openapi_contains_typed_read_models(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(self._database(directory))
            with TestClient(app) as client:
                schema = client.get("/openapi.json").json()

            components = schema.get("components", {}).get("schemas", {})
            for expected in (
                "ProjectReadModel",
                "ResourceReadModel",
                "DemandReadModel",
                "SegmentReadModel",
                "ShiftReadModel",
                "PlanningSnapshotReadModel",
            ):
                self.assertIn(expected, components)


if __name__ == "__main__":
    unittest.main()
