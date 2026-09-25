from __future__ import annotations

from datetime import date
from decimal import Decimal
import json
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from app.application.security import AuthPrincipal, ROLE_COORDINATOR
from app.infrastructure.sql import (
    AppUser,
    BusinessContact,
    Project,
    RequestLine,
    Resource,
    ResourceRequirement,
    TaskCatalogEntry,
    WorkforceRequest,
)
from app.server import create_api_app
from app.server.security import static_auth_resolver
from tests.sqlite_test_template import SqliteDatabaseTemplate


DAY = date(2026, 9, 25)


class CoordinatorDemandScopeTests(unittest.TestCase):
    @staticmethod
    def _seed_database(session) -> None:
        session.add_all(
            [
                BusinessContact(
                    id="C-A",
                    display_name="Coordonnateur Alpha",
                    email="coord-a-test-value",
                    active=True,
                ),
                BusinessContact(
                    id="C-B",
                    display_name="Coordonnateur Beta",
                    email="coord-b-test-value",
                    active=True,
                ),
                BusinessContact(
                    id="C-INACTIVE",
                    display_name="Coordonnateur inactif",
                    active=False,
                ),
                AppUser(
                    id="U-A",
                    issuer="urn:resourceplanner:local",
                    subject="coord-a",
                    display_name="Coordonnateur Alpha",
                    email="coord-a-test-value",
                    business_contact_id="C-A",
                    roles_json=json.dumps([ROLE_COORDINATOR]),
                    active=True,
                ),
                AppUser(
                    id="U-B",
                    issuer="urn:resourceplanner:local",
                    subject="coord-b",
                    display_name="Coordonnateur Beta",
                    email="coord-b-test-value",
                    business_contact_id="C-B",
                    roles_json=json.dumps([ROLE_COORDINATOR]),
                    active=True,
                ),
                AppUser(
                    id="U-NO-CONTACT",
                    issuer="urn:resourceplanner:local",
                    subject="coord-no-contact",
                    display_name="Coordonnateur Alpha",
                    email="coord-a-test-value",
                    business_contact_id=None,
                    roles_json=json.dumps([ROLE_COORDINATOR]),
                    active=True,
                ),
                Project(
                    id="P-SHARED",
                    number="P-410",
                    name="Projet partagé",
                    status="Actif",
                ),
                Resource(
                    id="R-A",
                    name="Ressource Alpha",
                    coordinator_contact_id="C-A",
                    active=True,
                ),
                Resource(
                    id="R-B",
                    name="Ressource Beta",
                    coordinator_contact_id="C-B",
                    active=True,
                ),
                Resource(
                    id="R-INACTIVE-CONTACT",
                    name="Ressource coordonnateur inactif",
                    coordinator_contact_id="C-INACTIVE",
                    active=True,
                ),
                TaskCatalogEntry(
                    id="T-A",
                    project_number="P-410",
                    task_code="210",
                    label="Automatisation Alpha",
                    coordinator_contact_id="C-A",
                    active=True,
                ),
                TaskCatalogEntry(
                    id="T-B",
                    project_number="P-410",
                    task_code="211",
                    label="Automatisation Beta",
                    coordinator_contact_id="C-B",
                    active=True,
                ),
            ]
        )
        session.flush()

        requests = [
            WorkforceRequest(
                id="D-A",
                legacy_demand_number="DMO-410-A",
                project_id="P-SHARED",
                status="Soumise",
                aggregate_version=1,
                line_mode=True,
            ),
            WorkforceRequest(
                id="D-B",
                legacy_demand_number="DMO-410-B",
                project_id="P-SHARED",
                status="Soumise",
                aggregate_version=1,
                line_mode=True,
            ),
            WorkforceRequest(
                id="D-MULTI",
                legacy_demand_number="DMO-410-MULTI",
                project_id="P-SHARED",
                status="Soumise",
                aggregate_version=1,
                line_mode=True,
            ),
            WorkforceRequest(
                id="D-TASK-A",
                legacy_demand_number="DMO-410-TASK-A",
                project_id="P-SHARED",
                status="Soumise",
                aggregate_version=1,
                line_mode=True,
            ),
            WorkforceRequest(
                id="D-INACTIVE",
                legacy_demand_number="DMO-410-INACTIVE",
                project_id="P-SHARED",
                status="Soumise",
                aggregate_version=1,
                line_mode=True,
            ),
            WorkforceRequest(
                id="D-APPROVED",
                legacy_demand_number="DMO-410-APPROVED",
                project_id="P-SHARED",
                status="Soumise",
                aggregate_version=4,
                line_mode=True,
            ),
            WorkforceRequest(
                id="D-PENDING",
                legacy_demand_number="DMO-410-PENDING",
                project_id="P-SHARED",
                status="En planification",
                cancellation_request_id="CYCLE-410",
                cancellation_state="PENDING",
                aggregate_version=3,
                line_mode=True,
            ),
            WorkforceRequest(
                id="D-CANCELLED",
                legacy_demand_number="DMO-410-CANCELLED",
                project_id="P-SHARED",
                status="Annulée",
                cancellation_request_id="CYCLE-CANCELLED",
                cancellation_state="ACCEPTED",
                aggregate_version=3,
                line_mode=True,
            ),
        ]
        session.add_all(requests)
        session.flush()

        session.add_all(
            [
                RequestLine(
                    id="L-A",
                    workforce_request_id="D-A",
                    position=0,
                    task_catalog_item_id="T-B",
                    proposed_resource_id="R-A",
                    active=True,
                ),
                RequestLine(
                    id="L-B",
                    workforce_request_id="D-B",
                    position=0,
                    task_catalog_item_id="T-B",
                    proposed_resource_id="R-B",
                    active=True,
                ),
                RequestLine(
                    id="L-MULTI-B",
                    workforce_request_id="D-MULTI",
                    position=0,
                    task_catalog_item_id="T-B",
                    proposed_resource_id="R-B",
                    active=True,
                ),
                RequestLine(
                    id="L-MULTI-A",
                    workforce_request_id="D-MULTI",
                    position=1,
                    task_catalog_item_id="T-A",
                    proposed_resource_id=None,
                    active=True,
                ),
                RequestLine(
                    id="L-TASK-A",
                    workforce_request_id="D-TASK-A",
                    position=0,
                    task_catalog_item_id="T-A",
                    proposed_resource_id=None,
                    active=True,
                ),
                RequestLine(
                    id="L-INACTIVE",
                    workforce_request_id="D-INACTIVE",
                    position=0,
                    task_catalog_item_id="T-A",
                    proposed_resource_id="R-INACTIVE-CONTACT",
                    active=True,
                ),
                RequestLine(
                    id="L-APPROVED",
                    workforce_request_id="D-APPROVED",
                    position=0,
                    task_catalog_item_id="T-B",
                    proposed_resource_id="R-B",
                    active=True,
                ),
                RequestLine(
                    id="L-PENDING",
                    workforce_request_id="D-PENDING",
                    position=0,
                    task_catalog_item_id="T-A",
                    proposed_resource_id="R-A",
                    active=True,
                ),
                RequestLine(
                    id="L-CANCELLED",
                    workforce_request_id="D-CANCELLED",
                    position=0,
                    task_catalog_item_id="T-A",
                    proposed_resource_id="R-A",
                    active=True,
                ),
            ]
        )
        session.flush()

        session.add_all(
            [
                ResourceRequirement(
                    id="REQ-APPROVED",
                    project_id="P-SHARED",
                    workforce_request_id="D-APPROVED",
                    source_request_line_id="L-APPROVED",
                    approved_task_catalog_item_id="T-A",
                    approved_request_version=3,
                    approved_contact_context_status="CAPTURED",
                    assigned_resource_id="R-A",
                    start_date=DAY,
                    end_date=DAY,
                    planned_hours=Decimal("8"),
                    status="Planifié",
                    origin="REQUEST",
                ),
                ResourceRequirement(
                    id="REQ-PENDING",
                    project_id="P-SHARED",
                    workforce_request_id="D-PENDING",
                    source_request_line_id="L-PENDING",
                    approved_task_catalog_item_id="T-A",
                    approved_request_version=3,
                    approved_contact_context_status="CAPTURED",
                    assigned_resource_id="R-A",
                    start_date=DAY,
                    end_date=DAY,
                    planned_hours=Decimal("8"),
                    status="Planifié",
                    origin="REQUEST",
                ),
                ResourceRequirement(
                    id="REQ-CANCELLED",
                    project_id="P-SHARED",
                    workforce_request_id="D-CANCELLED",
                    source_request_line_id="L-CANCELLED",
                    approved_task_catalog_item_id="T-A",
                    approved_request_version=2,
                    approved_contact_context_status="CAPTURED",
                    assigned_resource_id="R-A",
                    start_date=DAY,
                    end_date=DAY,
                    planned_hours=Decimal("8"),
                    status="Annulé",
                    origin="REQUEST",
                ),
            ]
        )

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._database_template = SqliteDatabaseTemplate(
            filename="coordinator-demand-scope.db",
            seed=cls._seed_database,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._database_template.cleanup()
        super().tearDownClass()

    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.database_url = self._database_template.copy_to(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _principal(user_id: str, *, display_name: str, email: str | None) -> AuthPrincipal:
        return AuthPrincipal.from_roles(
            local_user_id=user_id,
            issuer="urn:resourceplanner:local",
            subject=user_id.casefold(),
            display_name=display_name,
            email=email,
            roles=(ROLE_COORDINATOR,),
            auth_mode="local",
        )

    def _numbers(self, user_id: str, *, scope: str = "mine") -> set[str]:
        identities = {
            "U-A": ("Coordonnateur Alpha", "coord-a-test-value"),
            "U-B": ("Coordonnateur Beta", "coord-b-test-value"),
            "U-NO-CONTACT": (
                "Coordonnateur Alpha",
                "coord-a-test-value",
            ),
        }
        display_name, email = identities[user_id]
        app = create_api_app(
            self.database_url,
            auth_resolver=static_auth_resolver(
                self._principal(
                    user_id,
                    display_name=display_name,
                    email=email,
                )
            ),
        )
        with TestClient(app) as client:
            response = client.get("/api/v1/demands", params={"scope": scope})
        self.assertEqual(response.status_code, 200, response.text)
        return {row["number"] for row in response.json()}

    def test_two_coordinators_only_receive_their_submitted_requests(self) -> None:
        alpha = self._numbers("U-A")
        beta = self._numbers("U-B")

        self.assertIn("DMO-410-A", alpha)
        self.assertNotIn("DMO-410-B", alpha)
        self.assertIn("DMO-410-B", beta)
        self.assertNotIn("DMO-410-A", beta)

    def test_multiline_request_is_included_when_any_active_line_matches(self) -> None:
        self.assertIn("DMO-410-MULTI", self._numbers("U-A"))

    def test_task_coordinator_is_used_when_no_resource_coordinator_exists(self) -> None:
        self.assertIn("DMO-410-TASK-A", self._numbers("U-A"))

    def test_global_scope_is_unchanged(self) -> None:
        self.assertEqual(
            self._numbers("U-A", scope="global"),
            {
                "DMO-410-A",
                "DMO-410-B",
                "DMO-410-MULTI",
                "DMO-410-TASK-A",
                "DMO-410-INACTIVE",
                "DMO-410-APPROVED",
                "DMO-410-PENDING",
                "DMO-410-CANCELLED",
            },
        )

    def test_identity_without_business_contact_never_matches_name_or_email(self) -> None:
        self.assertEqual(self._numbers("U-NO-CONTACT"), set())

    def test_inactive_explicit_coordinator_does_not_fall_back_to_task(self) -> None:
        self.assertNotIn("DMO-410-INACTIVE", self._numbers("U-A"))

    def test_approved_context_wins_over_unapproved_candidate_change(self) -> None:
        alpha = self._numbers("U-A")
        beta = self._numbers("U-B")

        self.assertIn("DMO-410-APPROVED", alpha)
        self.assertNotIn("DMO-410-APPROVED", beta)

    def test_pending_cancellation_stays_visible_but_cancelled_plan_does_not(self) -> None:
        alpha = self._numbers("U-A")

        self.assertIn("DMO-410-PENDING", alpha)
        self.assertNotIn("DMO-410-CANCELLED", alpha)


if __name__ == "__main__":
    unittest.main()
