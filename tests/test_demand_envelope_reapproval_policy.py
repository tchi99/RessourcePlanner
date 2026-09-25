from __future__ import annotations

from datetime import date
import json
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.application.security import AuthPrincipal, ROLE_PROJECT_MANAGER
from app.infrastructure.sql import (
    Project,
    RequestApprovalReference,
    RequestApprovalRevision,
    ResourceRequirement,
    WorkforceRequest,
    WorkforceRequestHistory,
    create_session_factory,
    create_sql_engine,
)
from app.server import create_api_app
from app.server.security import static_auth_resolver
from tests.approval_test_support import routed_demand_payload, seed_test_approval_routing
from tests.http_test_auth import TEST_ADMIN_AUTH_RESOLVER
from tests.sqlite_test_template import SqliteDatabaseTemplate


D1 = date(2026, 9, 21)
D2 = date(2026, 9, 22)


def _project_manager_auth_resolver():
    return static_auth_resolver(
        AuthPrincipal.from_roles(
            local_user_id=None,
            issuer="urn:resourceplanner:test",
            subject="project-manager-13e",
            display_name="Chargé de projet 13E",
            email=None,
            roles=(ROLE_PROJECT_MANAGER,),
            auth_mode="test",
        )
    )


class DemandEnvelopeReapprovalPolicyTests(unittest.TestCase):
    @staticmethod
    def _seed_database(session) -> None:
        session.add(Project(id="P1", number="P-1", name="Projet 13E"))
        seed_test_approval_routing(session, map_existing_tasks=True)

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._database_template = SqliteDatabaseTemplate(
            filename="demand-envelope-13e.db",
            seed=cls._seed_database,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._database_template.cleanup()
        super().tearDownClass()

    def _database(self, directory: str) -> str:
        return self._database_template.copy_to(directory)

    @staticmethod
    def _create_and_approve(
        database_url: str,
        *,
        hours: float = 100,
    ) -> str:
        app = create_api_app(
            database_url,
            actor_name="admin-13e",
            auth_resolver=TEST_ADMIN_AUTH_RESOLVER,
        )
        with TestClient(app, raise_server_exceptions=False) as client:
            created = client.post(
                "/api/v1/demands",
                json=routed_demand_payload({
                    "project_number": "P-1",
                    "desired_start": D1.isoformat(),
                    "desired_end": D2.isoformat(),
                    "estimated_hours": hours,
                    "submit": True,
                }),
            )
            assert created.status_code == 201, created.text
            number = created.json()["demand_number"]
            approved = client.post(
                f"/api/v1/demands/{number}/approve",
                json={"comment": "Autorisation initiale 13E"},
            )
            assert approved.status_code == 200, approved.text
            return number

    @staticmethod
    def _request(session, number: str) -> WorkforceRequest:
        request = session.scalar(
            select(WorkforceRequest).where(
                WorkforceRequest.legacy_demand_number == number
            )
        )
        assert request is not None
        return request

    @staticmethod
    def _active_requirement(
        session,
        request_id: str,
    ) -> ResourceRequirement:
        rows = session.scalars(
            select(ResourceRequirement).where(
                ResourceRequirement.workforce_request_id == request_id,
                ResourceRequirement.status != "Annulé",
            )
        ).all()
        assert len(rows) == 1, rows
        return rows[0]

    def test_project_manager_twenty_percent_is_within_envelope_and_audited(self) -> None:
        with TemporaryDirectory() as directory:
            database_url = self._database(directory)
            number = self._create_and_approve(database_url)

            engine = create_sql_engine(database_url)
            factory = create_session_factory(engine)
            try:
                with factory() as session:
                    request = self._request(session, number)
                    reference = session.get(RequestApprovalReference, request.id)
                    assert reference is not None
                    original_revision = reference.active_revision_id
                    self.assertEqual(
                        self._active_requirement(session, request.id).planned_hours,
                        100,
                    )
            finally:
                engine.dispose()

            pm_app = create_api_app(
                database_url,
                actor_name="pm-13e",
                auth_resolver=_project_manager_auth_resolver(),
            )
            with TestClient(pm_app, raise_server_exceptions=False) as client:
                patched = client.patch(
                    f"/api/v1/demands/{number}",
                    json={
                        "estimated_hours": 120,
                        "comment": "Tolérance PM exacte +20%",
                    },
                )
                self.assertEqual(patched.status_code, 200, patched.text)
                self.assertFalse(patched.json()["reapproval_required"])
                demand = client.get(f"/api/v1/demands/{number}")
                self.assertEqual(demand.status_code, 200, demand.text)
                self.assertEqual(demand.json()["status"], "En planification")
                self.assertEqual(demand.json()["estimated_hours"], 120)

            engine = create_sql_engine(database_url)
            factory = create_session_factory(engine)
            try:
                with factory() as session:
                    request = self._request(session, number)
                    reference = session.get(RequestApprovalReference, request.id)
                    assert reference is not None
                    self.assertEqual(reference.active_revision_id, original_revision)
                    self.assertEqual(
                        self._active_requirement(session, request.id).planned_hours,
                        120,
                    )
                    revision_count = session.scalar(
                        select(func.count(RequestApprovalRevision.id)).where(
                            RequestApprovalRevision.workforce_request_id == request.id
                        )
                    )
                    self.assertEqual(revision_count, 1)
                    audit = session.scalar(
                        select(WorkforceRequestHistory)
                        .where(
                            WorkforceRequestHistory.workforce_request_id == request.id,
                            WorkforceRequestHistory.action
                            == "Comparaison enveloppe approuvée",
                        )
                        .order_by(WorkforceRequestHistory.occurred_at.desc())
                    )
                    self.assertIsNotNone(audit)
                    assert audit is not None
                    details = json.loads(audit.details or "{}")
                    decision = details["envelope_decision"]
                    self.assertEqual(decision["decision"], "WITHIN_ENVELOPE")
                    self.assertEqual(decision["reason"], "DELEGATED_TOLERANCE")
                    delegated = next(
                        row
                        for row in decision["changes"]
                        if row["code"] == "DELEGATED_TOLERANCE"
                    )
                    self.assertEqual(delegated["reference_hours"], "100.00")
                    self.assertEqual(delegated["candidate_hours"], "120.00")
                    self.assertEqual(delegated["delta_percent"], "20.00")
            finally:
                engine.dispose()

    def test_project_manager_above_twenty_percent_requires_reapproval_and_keeps_old_plan(self) -> None:
        with TemporaryDirectory() as directory:
            database_url = self._database(directory)
            number = self._create_and_approve(database_url)

            engine = create_sql_engine(database_url)
            factory = create_session_factory(engine)
            try:
                with factory() as session:
                    request = self._request(session, number)
                    reference = session.get(RequestApprovalReference, request.id)
                    assert reference is not None
                    original_revision = reference.active_revision_id
            finally:
                engine.dispose()

            pm_app = create_api_app(
                database_url,
                actor_name="pm-13e",
                auth_resolver=_project_manager_auth_resolver(),
            )
            with TestClient(pm_app, raise_server_exceptions=False) as client:
                patched = client.patch(
                    f"/api/v1/demands/{number}",
                    json={
                        "estimated_hours": 121,
                        "comment": "Au-delà de la tolérance PM",
                    },
                )
                self.assertEqual(patched.status_code, 200, patched.text)
                self.assertTrue(patched.json()["reapproval_required"])
                self.assertEqual(patched.json()["status"], "Soumise")

            engine = create_sql_engine(database_url)
            factory = create_session_factory(engine)
            try:
                with factory() as session:
                    request = self._request(session, number)
                    self.assertEqual(request.status, "Soumise")
                    reference = session.get(RequestApprovalReference, request.id)
                    assert reference is not None
                    self.assertEqual(reference.active_revision_id, original_revision)
                    self.assertEqual(
                        self._active_requirement(session, request.id).planned_hours,
                        100,
                    )
                    revision_count = session.scalar(
                        select(func.count(RequestApprovalRevision.id)).where(
                            RequestApprovalRevision.workforce_request_id == request.id
                        )
                    )
                    self.assertEqual(revision_count, 1)
            finally:
                engine.dispose()

            admin_app = create_api_app(
                database_url,
                actor_name="admin-13e",
                auth_resolver=TEST_ADMIN_AUTH_RESOLVER,
            )
            with TestClient(admin_app, raise_server_exceptions=False) as client:
                approved = client.post(
                    f"/api/v1/demands/{number}/approve",
                    json={"comment": "Réapprobation 121h"},
                )
                self.assertEqual(approved.status_code, 200, approved.text)

            engine = create_sql_engine(database_url)
            factory = create_session_factory(engine)
            try:
                with factory() as session:
                    request = self._request(session, number)
                    reference = session.get(RequestApprovalReference, request.id)
                    assert reference is not None
                    self.assertNotEqual(reference.active_revision_id, original_revision)
                    current_revision = session.get(
                        RequestApprovalRevision,
                        reference.active_revision_id,
                    )
                    assert current_revision is not None
                    self.assertEqual(
                        current_revision.previous_revision_id,
                        original_revision,
                    )
                    self.assertEqual(
                        self._active_requirement(session, request.id).planned_hours,
                        121,
                    )
            finally:
                engine.dispose()

    def test_admin_widening_directly_creates_and_activates_new_revision(self) -> None:
        with TemporaryDirectory() as directory:
            database_url = self._database(directory)
            number = self._create_and_approve(database_url)

            engine = create_sql_engine(database_url)
            factory = create_session_factory(engine)
            try:
                with factory() as session:
                    request = self._request(session, number)
                    reference = session.get(RequestApprovalReference, request.id)
                    assert reference is not None
                    original_revision = reference.active_revision_id
            finally:
                engine.dispose()

            admin_app = create_api_app(
                database_url,
                actor_name="admin-13e",
                auth_resolver=TEST_ADMIN_AUTH_RESOLVER,
            )
            with TestClient(admin_app, raise_server_exceptions=False) as client:
                patched = client.patch(
                    f"/api/v1/demands/{number}",
                    json={
                        "estimated_hours": 150,
                        "comment": "Élargissement direct par approbateur",
                    },
                )
                self.assertEqual(patched.status_code, 200, patched.text)
                self.assertFalse(patched.json()["reapproval_required"])
                demand = client.get(f"/api/v1/demands/{number}")
                self.assertEqual(demand.status_code, 200, demand.text)
                self.assertEqual(demand.json()["status"], "En planification")

            engine = create_sql_engine(database_url)
            factory = create_session_factory(engine)
            try:
                with factory() as session:
                    request = self._request(session, number)
                    reference = session.get(RequestApprovalReference, request.id)
                    assert reference is not None
                    self.assertNotEqual(reference.active_revision_id, original_revision)
                    current_revision = session.get(
                        RequestApprovalRevision,
                        reference.active_revision_id,
                    )
                    assert current_revision is not None
                    self.assertEqual(
                        current_revision.previous_revision_id,
                        original_revision,
                    )
                    self.assertEqual(
                        self._active_requirement(session, request.id).planned_hours,
                        150,
                    )
                    revisions = session.scalars(
                        select(RequestApprovalRevision)
                        .where(
                            RequestApprovalRevision.workforce_request_id == request.id
                        )
                        .order_by(RequestApprovalRevision.created_at)
                    ).all()
                    self.assertEqual(len(revisions), 2)
                    self.assertEqual(revisions[0].id, original_revision)
                    direct_audit = session.scalar(
                        select(WorkforceRequestHistory)
                        .where(
                            WorkforceRequestHistory.workforce_request_id == request.id,
                            WorkforceRequestHistory.action
                            == "Autorisation élargie par approbateur",
                        )
                        .order_by(WorkforceRequestHistory.occurred_at.desc())
                    )
                    self.assertIsNotNone(direct_audit)
            finally:
                engine.dispose()


if __name__ == "__main__":
    unittest.main()
