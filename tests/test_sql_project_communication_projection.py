from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from app.application.operational_contacts import OperationalContactService
from app.application.project_communications import ProjectCommunicationService
from app.infrastructure.sql import (
    AppUser,
    Base,
    BusinessContact,
    Project,
    RequestLine,
    Resource,
    ResourceRequirement,
    Shift,
    TaskCatalogEntry,
    WorkforceRequest,
    create_session_factory,
    create_sql_engine,
)
from app.infrastructure.sql.operational_contact_repository import (
    SqlOperationalContactRepository,
)
from app.infrastructure.sql.project_communication_repository import (
    DIAGNOSTIC_RESOURCE_USER_LINK_MISSING,
    SqlProjectCommunicationRepository,
)
from app.server import create_api_app
from tests.http_test_auth import TEST_ADMIN_AUTH_RESOLVER


WEEK = date(2026, 9, 21)
TEST_DOMAIN = "example.test"


class SqlProjectCommunicationProjectionTests(unittest.TestCase):
    @staticmethod
    def _seed(session) -> None:
        pm_email = "pm" + chr(64) + TEST_DOMAIN
        tech_email = "tech" + chr(64) + TEST_DOMAIN
        legacy_email = "legacy" + chr(64) + TEST_DOMAIN
        session.add_all(
            [
                BusinessContact(
                    id="C-PM",
                    display_name="Chargé de projet Démo",
                    email=pm_email,
                    source="APP_USER",
                ),
                BusinessContact(
                    id="C-RESP",
                    display_name="Responsable approuvé",
                    phone="555" + "-" + "0100",
                    source="APP_USER",
                ),
                BusinessContact(
                    id="C-R1",
                    display_name="Technicien profil",
                    email=tech_email,
                    source="APP_USER",
                ),
                BusinessContact(
                    id="C-CURRENT",
                    display_name="Responsable courant",
                    source="APP_USER",
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                AppUser(
                    id="U-PM",
                    issuer="urn:test",
                    subject="pm",
                    display_name="Chargé de projet Démo",
                    email=pm_email,
                    employee_external_id="PM-1",
                    business_contact_id="C-PM",
                    roles_json='["PROJECT_MANAGER"]',
                    active=True,
                ),
                AppUser(
                    id="U-RESP",
                    issuer="urn:test",
                    subject="resp",
                    display_name="Responsable approuvé",
                    email=None,
                    employee_external_id="RESP-1",
                    business_contact_id="C-RESP",
                    roles_json='["PROJECT_MANAGER"]',
                    active=True,
                ),
                AppUser(
                    id="U-R1",
                    issuer="urn:test",
                    subject="tech",
                    display_name="Technicien profil",
                    email=tech_email,
                    employee_external_id="EMP-1",
                    business_contact_id="C-R1",
                    roles_json='["TECHNICIAN"]',
                    active=True,
                ),
                AppUser(
                    id="U-CURRENT",
                    issuer="urn:test",
                    subject="current",
                    display_name="Responsable courant",
                    email=None,
                    employee_external_id="RESP-2",
                    business_contact_id="C-CURRENT",
                    roles_json='["PROJECT_MANAGER"]',
                    active=True,
                ),
            ]
        )
        session.add(
            Project(
                id="P1",
                number="1000",
                name="Projet projection",
                project_manager_external_id="LEGACY-PM",
                project_manager_name="Ancien nom",
                project_manager_contact_id="C-PM",
                status="Actif",
            )
        )
        session.add_all(
            [
                TaskCatalogEntry(
                    id="T-APPROVED",
                    project_number="1000",
                    task_code="210",
                    label="Tâche approuvée",
                    operational_responsible_contact_id="C-RESP",
                    active=True,
                ),
                TaskCatalogEntry(
                    id="T-CURRENT",
                    project_number="1000",
                    task_code="220",
                    label="Tâche courante",
                    operational_responsible_contact_id="C-CURRENT",
                    active=True,
                ),
                Resource(
                    id="R1",
                    external_id="EMP-1",
                    name="Technicien ressource",
                    email=legacy_email,
                    active=True,
                ),
                Resource(
                    id="R2",
                    external_id="EMP-2",
                    name="Ressource sans utilisateur",
                    email=legacy_email,
                    active=True,
                ),
            ]
        )
        session.flush()
        session.add(
            WorkforceRequest(
                id="D1",
                legacy_demand_number="DMO-290A-1",
                project_id="P1",
                description="Description courante de la demande",
                aggregate_version=4,
                line_mode=True,
            )
        )
        session.flush()
        session.add(
            RequestLine(
                id="L1",
                workforce_request_id="D1",
                position=0,
                task_catalog_item_id="T-CURRENT",
                erp_task_code="220",
                erp_task_label="Tâche courante",
                description="Description modifiée non approuvée",
            )
        )
        session.add_all(
            [
                ResourceRequirement(
                    id="REQ1",
                    project_id="P1",
                    workforce_request_id="D1",
                    source_request_line_id="L1",
                    approved_task_catalog_item_id="T-APPROVED",
                    approved_request_version=3,
                    approved_contact_context_status="CAPTURED",
                    assigned_resource_id="R1",
                    start_date=WEEK,
                    end_date=WEEK,
                    planned_hours=Decimal("8"),
                    description="Installation approuvée",
                    status="Planifié",
                    origin="REQUEST",
                ),
                ResourceRequirement(
                    id="REQ2",
                    project_id="P1",
                    workforce_request_id="D1",
                    source_request_line_id="L1",
                    approved_task_catalog_item_id="T-APPROVED",
                    approved_request_version=3,
                    approved_contact_context_status="CAPTURED",
                    assigned_resource_id="R2",
                    start_date=WEEK,
                    end_date=WEEK,
                    planned_hours=Decimal("4"),
                    description="Installation approuvée",
                    status="Planifié",
                    origin="REQUEST",
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                Shift(
                    id="S1",
                    resource_requirement_id="REQ1",
                    resource_id="R1",
                    work_date=WEEK,
                    hours=Decimal("8"),
                    allocation_type="Flexible",
                    outside_standard_hours=False,
                ),
                Shift(
                    id="S2",
                    resource_requirement_id="REQ2",
                    resource_id="R2",
                    work_date=WEEK,
                    hours=Decimal("4"),
                    allocation_type="Flexible",
                    outside_standard_hours=True,
                ),
            ]
        )

    def _database(self, directory: str) -> str:
        path = Path(directory) / "project-communication.db"
        url = f"sqlite+pysqlite:///{path.as_posix()}"
        engine = create_sql_engine(url)
        Base.metadata.create_all(engine)
        factory = create_session_factory(engine)
        with factory.begin() as session:
            self._seed(session)
        engine.dispose()
        return url

    @staticmethod
    def _service(session) -> ProjectCommunicationService:
        operational = OperationalContactService(
            SqlOperationalContactRepository(session)
        )
        return ProjectCommunicationService(
            SqlProjectCommunicationRepository(
                session,
                operational_contacts=operational,
            )
        )

    def test_projection_uses_approved_context_and_user_backed_contacts(self) -> None:
        with TemporaryDirectory() as directory:
            url = self._database(directory)
            engine = create_sql_engine(url)
            factory = create_session_factory(engine)
            try:
                with factory() as session:
                    projection = self._service(session).project_projection(
                        week_start=WEEK
                    )
            finally:
                engine.dispose()

        project = projection.projects[0]
        self.assertEqual(project.project_manager.display_name, "Chargé de projet Démo")
        self.assertEqual(project.project_manager.email, "pm" + chr(64) + TEST_DOMAIN)
        task = project.days[0].tasks[0]
        self.assertEqual(task.task_description, "Installation approuvée")
        self.assertEqual(task.task_ids, ("T-APPROVED",))
        self.assertEqual(
            task.operational_responsibles[0].display_name,
            "Responsable approuvé",
        )
        tech = next(row for row in task.resources if row.resource_id == "R1")
        self.assertEqual(tech.contact.email, "tech" + chr(64) + TEST_DOMAIN)
        self.assertNotEqual(tech.contact.email, "legacy" + chr(64) + TEST_DOMAIN)

    def test_unlinked_resource_is_explicitly_diagnosed(self) -> None:
        with TemporaryDirectory() as directory:
            url = self._database(directory)
            engine = create_sql_engine(url)
            factory = create_session_factory(engine)
            try:
                with factory() as session:
                    projection = self._service(session).project_projection(
                        week_start=WEEK
                    )
            finally:
                engine.dispose()

        resources = projection.projects[0].days[0].tasks[0].resources
        missing = next(row for row in resources if row.resource_id == "R2")
        self.assertIsNone(missing.contact.email)
        self.assertIn(DIAGNOSTIC_RESOURCE_USER_LINK_MISSING, missing.diagnostics)

    def test_http_preview_exposes_one_project_message_with_to_cc_and_diagnostics(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(
                self._database(directory),
                auth_resolver=TEST_ADMIN_AUTH_RESOLVER,
            )
            with TestClient(app) as client:
                response = client.get(
                    "/api/v1/communications/project-preview"
                    "?week_start=2026-09-23"
                )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(len(payload["drafts"]), 1)
        draft = payload["drafts"][0]
        self.assertEqual(draft["message_key"], "project:P1")
        self.assertEqual(draft["audience"], "project")
        self.assertEqual(
            draft["to_recipient"]["email"],
            "pm" + chr(64) + TEST_DOMAIN,
        )
        self.assertEqual(
            [row["email"] for row in draft["cc_recipients"]],
            ["tech" + chr(64) + TEST_DOMAIN],
        )
        self.assertTrue(draft["approvable"])
        self.assertIn("Responsable approuvé", draft["body"])
        self.assertIn("555" + "-" + "0100", draft["body"])
        self.assertTrue(
            any(
                row["code"] == "PROJECT_CC_EMAIL_MISSING"
                and row["entity_id"] == "R2"
                for row in draft["diagnostics"]
            )
        )

    def test_http_contract_exposes_project_projection_under_communications(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(
                self._database(directory),
                auth_resolver=TEST_ADMIN_AUTH_RESOLVER,
            )
            with TestClient(app) as client:
                response = client.get(
                    "/api/v1/communications/project-projection"
                    "?week_start=2026-09-23"
                )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["week_start"], "2026-09-21")
        self.assertEqual(payload["week_end"], "2026-09-27")
        self.assertEqual(payload["projects"][0]["project_number"], "1000")
        self.assertEqual(
            payload["projects"][0]["days"][0]["tasks"][0]["task_description"],
            "Installation approuvée",
        )


if __name__ == "__main__":
    unittest.main()
