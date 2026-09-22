from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from app.domain.operational_contacts import (
    SOURCE_RESOURCE_COORDINATOR,
    SOURCE_TASK_RESPONSIBLE,
)
from app.infrastructure.sql import (
    Base,
    BusinessContact,
    Project,
    RequestLine,
    Resource,
    ResourceRequirement,
    Shift,
    TaskCatalogEntry,
    WorkforceRequest,
    WorkforceRequestPeriod,
    WorkforceRequestPeriodSelection,
    create_session_factory,
    create_sql_engine,
)
from app.server import create_api_app
from tests.http_test_auth import (
    TEST_ADMIN_AUTH_RESOLVER,
    TEST_PROJECT_MANAGER_AUTH_RESOLVER,
)


D1 = date(2026, 9, 23)
D2 = date(2026, 9, 24)


class DemandDetailApiTests(unittest.TestCase):
    @staticmethod
    def _database(directory: str, *, status: str = "Soumise") -> str:
        path = Path(directory) / "demand-detail.db"
        url = f"sqlite+pysqlite:///{path.as_posix()}"
        engine = create_sql_engine(url)
        Base.metadata.create_all(engine)
        factory = create_session_factory(engine)
        with factory.begin() as session:
            session.add_all(
                [
                    BusinessContact(
                        id="C-PM",
                        display_name="Chargé projet",
                    ),
                    BusinessContact(
                        id="C-TASK",
                        display_name="Responsable tâche",
                    ),
                    BusinessContact(
                        id="C-COORD",
                        display_name="Coordonnateur ressource",
                    ),
                    Project(
                        id="P1",
                        number="P-1",
                        name="Projet détail",
                        project_manager_contact_id="C-PM",
                    ),
                    TaskCatalogEntry(
                        id="T1",
                        project_number="P-1",
                        task_code="210",
                        label="Programmation",
                        operational_responsible_contact_id="C-TASK",
                        active=True,
                    ),
                    Resource(
                        id="R-PROPOSED",
                        name="Ressource proposée",
                        coordinator_contact_id="C-COORD",
                        active=True,
                    ),
                    Resource(
                        id="R-TARGET",
                        name="Cible automatique",
                        active=True,
                    ),
                    Resource(
                        id="R-ACTUAL",
                        name="Ressource réellement affectée",
                        active=True,
                    ),
                ]
            )
            session.flush()
            session.add(
                WorkforceRequest(
                    id="D1",
                    legacy_demand_number="DMO-329-1",
                    project_id="P1",
                    requester_name="Demandeur",
                    status=status,
                    aggregate_version=7,
                    line_mode=True,
                )
            )
            session.flush()
            session.add_all(
                [
                    RequestLine(
                        id="L1",
                        workforce_request_id="D1",
                        position=0,
                        desired_start=D1,
                        desired_end=D2,
                        estimated_hours=8,
                        task_catalog_item_id="T1",
                        proposed_resource_id="R-PROPOSED",
                        description="Ligne principale",
                    ),
                    RequestLine(
                        id="L2",
                        workforce_request_id="D1",
                        position=1,
                        desired_start=D2,
                        desired_end=D2,
                        estimated_hours=4,
                        description="Ligne secondaire",
                    ),
                ]
            )
            session.flush()
            session.add_all(
                [
                    WorkforceRequestPeriod(
                        id="PER-A",
                        period_key="OPT-A",
                        workforce_request_id="D1",
                        request_line_id="L1",
                        sequence=1,
                        kind="ALTERNATIVE",
                        alternative_group="VISITE",
                        start_date=D1,
                        end_date=D1,
                        hours=8,
                        confirmation="Tentative",
                    ),
                    WorkforceRequestPeriod(
                        id="PER-B",
                        period_key="OPT-B",
                        workforce_request_id="D1",
                        request_line_id="L1",
                        sequence=2,
                        kind="ALTERNATIVE",
                        alternative_group="VISITE",
                        start_date=D2,
                        end_date=D2,
                        hours=8,
                        confirmation="Tentative",
                    ),
                    WorkforceRequestPeriod(
                        id="PER-C",
                        period_key="CUM-1",
                        workforce_request_id="D1",
                        request_line_id="L2",
                        sequence=1,
                        kind="CUMULATIVE",
                        start_date=D2,
                        end_date=D2,
                        hours=4,
                        confirmation="Confirmée",
                    ),
                ]
            )
            session.flush()
            session.add(
                WorkforceRequestPeriodSelection(
                    workforce_request_id="D1",
                    request_line_id="L1",
                    alternative_group="VISITE",
                    period_id="PER-B",
                    selected_at=datetime.now(timezone.utc),
                    selected_by_name="Coordonnateur",
                )
            )
            session.add(
                ResourceRequirement(
                    id="REQ1",
                    legacy_segment_id="SEG-329-1",
                    project_id="P1",
                    workforce_request_id="D1",
                    source_request_line_id="L1",
                    assigned_resource_id="R-TARGET",
                    start_date=D1,
                    end_date=D2,
                    planned_hours=8,
                    status="Planifié",
                    origin="REQUEST",
                )
            )
            session.flush()
            session.add(
                Shift(
                    id="SHIFT1",
                    resource_requirement_id="REQ1",
                    resource_id="R-ACTUAL",
                    work_date=D1,
                    hours=6,
                    source="MANUAL",
                    locked=True,
                )
            )
        engine.dispose()
        return url

    def test_detail_composes_lines_periods_contacts_plan_and_version(self) -> None:
        with TemporaryDirectory() as directory:
            database_url = self._database(directory)
            app = create_api_app(
                database_url,
                auth_resolver=TEST_PROJECT_MANAGER_AUTH_RESOLVER,
            )
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.get("/api/v1/demands/DMO-329-1/detail")

            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            self.assertEqual(body["version"], 7)
            self.assertEqual(body["demand"]["number"], "DMO-329-1")
            self.assertEqual(len(body["lines"]), 2)
            by_line = {row["line"]["line_id"]: row for row in body["lines"]}

            line = by_line["L1"]
            self.assertEqual(
                [row["period_id"] for row in line["periods"]],
                ["OPT-A", "OPT-B"],
            )
            self.assertEqual(
                line["alternative_groups"][0]["selected_period_id"],
                "OPT-B",
            )
            self.assertEqual(
                line["contacts"]["operational_responsible"]["source_type"],
                SOURCE_TASK_RESPONSIBLE,
            )
            self.assertEqual(
                line["contacts"]["coordinator"]["source_type"],
                SOURCE_RESOURCE_COORDINATOR,
            )

            plan = body["materialized_plan"]
            self.assertEqual(plan["requirement_count"], 1)
            self.assertEqual(plan["planned_hours"], 8.0)
            self.assertEqual(plan["covered_hours"], 6.0)
            requirement = plan["requirements"][0]
            self.assertEqual(requirement["source_request_line_id"], "L1")
            self.assertEqual(
                requirement["automatic_target_resource_id"],
                "R-TARGET",
            )
            self.assertEqual(
                requirement["mobilized_resources"][0]["resource_id"],
                "R-ACTUAL",
            )
            self.assertEqual(
                body["policy"]["expected_request_version"],
                7,
            )

    def test_detail_actions_follow_current_role_and_request_state(self) -> None:
        with TemporaryDirectory() as directory:
            database_url = self._database(directory, status="Soumise")
            pm_app = create_api_app(
                database_url,
                auth_resolver=TEST_PROJECT_MANAGER_AUTH_RESOLVER,
            )
            admin_app = create_api_app(
                database_url,
                auth_resolver=TEST_ADMIN_AUTH_RESOLVER,
            )
            with TestClient(pm_app, raise_server_exceptions=False) as client:
                pm = client.get("/api/v1/demands/DMO-329-1/detail")
            with TestClient(admin_app, raise_server_exceptions=False) as client:
                admin = client.get("/api/v1/demands/DMO-329-1/detail")

            self.assertEqual(pm.status_code, 200, pm.text)
            self.assertEqual(admin.status_code, 200, admin.text)
            self.assertNotIn("approve", pm.json()["workflow"]["available_actions"])
            self.assertIn("approve", admin.json()["workflow"]["available_actions"])
            self.assertTrue(pm.json()["policy"]["can_modify_candidate"])

    def test_detail_supports_legacy_single_line_request(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "demand-detail-simple.db"
            database_url = f"sqlite+pysqlite:///{path.as_posix()}"
            engine = create_sql_engine(database_url)
            Base.metadata.create_all(engine)
            factory = create_session_factory(engine)
            with factory.begin() as session:
                session.add(
                    Project(id="P1", number="P-1", name="Projet simple")
                )
                session.flush()
                session.add(
                    WorkforceRequest(
                        id="D-SIMPLE",
                        legacy_demand_number="DMO-329-SIMPLE",
                        project_id="P1",
                        status="Brouillon",
                        aggregate_version=3,
                        line_mode=False,
                        desired_start=D1,
                        desired_end=D1,
                        estimated_hours=4,
                    )
                )
                session.flush()
                session.add(
                    RequestLine(
                        id="D-SIMPLE",
                        workforce_request_id="D-SIMPLE",
                        position=0,
                        desired_start=D1,
                        desired_end=D1,
                        estimated_hours=4,
                    )
                )
                session.flush()
                session.add(
                    WorkforceRequestPeriod(
                        id="PER-SIMPLE",
                        period_key="SIMPLE-1",
                        workforce_request_id="D-SIMPLE",
                        request_line_id="D-SIMPLE",
                        sequence=1,
                        kind="CUMULATIVE",
                        start_date=D1,
                        end_date=D1,
                        hours=4,
                        confirmation="Confirmée",
                    )
                )
            engine.dispose()

            app = create_api_app(
                database_url,
                auth_resolver=TEST_PROJECT_MANAGER_AUTH_RESOLVER,
            )
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.get(
                    "/api/v1/demands/DMO-329-SIMPLE/detail"
                )

            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            self.assertEqual(body["version"], 3)
            self.assertEqual(len(body["lines"]), 1)
            self.assertEqual(
                body["lines"][0]["periods"][0]["period_id"],
                "SIMPLE-1",
            )

    def test_unknown_demand_detail_uses_structured_not_found(self) -> None:
        with TemporaryDirectory() as directory:
            database_url = self._database(directory)
            app = create_api_app(
                database_url,
                auth_resolver=TEST_ADMIN_AUTH_RESOLVER,
            )
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.get("/api/v1/demands/UNKNOWN/detail")

            self.assertEqual(response.status_code, 404)
            self.assertEqual(
                response.json()["error"]["code"],
                "demand_not_found",
            )


if __name__ == "__main__":
    unittest.main()
