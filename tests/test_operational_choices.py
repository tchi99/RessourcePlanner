from __future__ import annotations

from datetime import date
import json
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.infrastructure.sql import (
    Project,
    RequestApprovalRevision,
    RequestOperationalState,
    ResourceRequirement,
    WorkforceRequest,
    create_session_factory,
    create_sql_engine,
)
from app.server import create_api_app
from tests.http_test_auth import TEST_ADMIN_AUTH_RESOLVER
from tests.sqlite_test_template import SqliteDatabaseTemplate


D1 = date(2026, 9, 21)
D2 = date(2026, 9, 22)
D3 = date(2026, 9, 23)
D4 = date(2026, 9, 24)


class VersionedOperationalChoicesApiTests(unittest.TestCase):
    @staticmethod
    def _seed_database(session) -> None:
        session.add(Project(id="P1", number="P-1", name="Projet 13D"))

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._database_template = SqliteDatabaseTemplate(
            filename="operational-choices-13d.db",
            seed=cls._seed_database,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._database_template.cleanup()
        super().tearDownClass()

    def _database(self, directory: str) -> str:
        return self._database_template.copy_to(directory)

    @staticmethod
    def _create_line(client: TestClient, *, confirmation: str = "Tentative") -> tuple[str, str]:
        created = client.post(
            "/api/v1/demands",
            json={
                "project_number": "P-1",
                "priority": "Normale",
                "lines": [
                    {
                        "desired_start": D1.isoformat(),
                        "desired_end": D2.isoformat(),
                        "estimated_hours": 8,
                        "desired_active_days": 1,
                        "confirmation": confirmation,
                    }
                ],
            },
        )
        assert created.status_code == 201, created.text
        number = created.json()["demand_number"]
        demand = client.get(f"/api/v1/demands/{number}")
        assert demand.status_code == 200, demand.text
        line_id = demand.json()["lines"][0]["line_id"]
        return number, line_id

    @staticmethod
    def _alternatives(day_a: date, day_b: date) -> dict[str, object]:
        return {
            "periods": [
                {
                    "period_id": "OPT-A",
                    "start_date": day_a.isoformat(),
                    "end_date": day_a.isoformat(),
                    "hours": 8,
                    "kind": "ALTERNATIVE",
                    "alternative_group": "VISITE",
                    "confirmation": "Tentative",
                    "desired_active_days": 1,
                },
                {
                    "period_id": "OPT-B",
                    "start_date": day_b.isoformat(),
                    "end_date": day_b.isoformat(),
                    "hours": 8,
                    "kind": "ALTERNATIVE",
                    "alternative_group": "VISITE",
                    "confirmation": "Tentative",
                    "desired_active_days": 1,
                },
            ]
        }

    @staticmethod
    def _active_requirements(session, request_id: str) -> list[ResourceRequirement]:
        return list(
            session.scalars(
                select(ResourceRequirement)
                .where(
                    ResourceRequirement.workforce_request_id == request_id,
                    ResourceRequirement.status != "Annulé",
                )
                .order_by(ResourceRequirement.created_at, ResourceRequirement.id)
            ).all()
        )

    def test_candidate_selection_is_distinct_from_active_selection_and_old_snapshot_drives_resync(self) -> None:
        with TemporaryDirectory() as directory:
            database_url = self._database(directory)
            app = create_api_app(
                database_url,
                actor_name="coord-13d",
                auth_resolver=TEST_ADMIN_AUTH_RESOLVER,
            )
            with TestClient(app, raise_server_exceptions=False) as client:
                number, line_id = self._create_line(client)
                periods = client.put(
                    f"/api/v1/demands/{number}/lines/{line_id}/periods",
                    json=self._alternatives(D1, D2),
                )
                self.assertEqual(periods.status_code, 200, periods.text)
                selected = client.put(
                    f"/api/v1/demands/{number}/lines/{line_id}/alternative-groups/VISITE/selection",
                    json={"period_id": "OPT-A"},
                )
                self.assertEqual(selected.status_code, 200, selected.text)
                submitted = client.post(f"/api/v1/demands/{number}/submit")
                self.assertEqual(submitted.status_code, 200, submitted.text)
                approved = client.post(
                    f"/api/v1/demands/{number}/approve",
                    json={"comment": "Approbation 13D"},
                )
                self.assertEqual(approved.status_code, 200, approved.text)

                # Edit only the candidate after approval. The active plan must not
                # silently adopt these new dates or the new candidate selection.
                replaced = client.put(
                    f"/api/v1/demands/{number}/lines/{line_id}/periods",
                    json=self._alternatives(D3, D4),
                )
                self.assertEqual(replaced.status_code, 200, replaced.text)
                self.assertTrue(replaced.json()["reapproval_required"])
                candidate_selected = client.put(
                    f"/api/v1/demands/{number}/lines/{line_id}/alternative-groups/VISITE/selection",
                    json={"period_id": "OPT-B"},
                )
                self.assertEqual(candidate_selected.status_code, 200, candidate_selected.text)
                self.assertIsNone(candidate_selected.json()["planning"])

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
                    self.assertEqual(request.status, "Soumise")
                    state = session.get(RequestOperationalState, request.id)
                    assert state is not None
                    self.assertEqual(state.version, 1)
                    self.assertIn("OPT-A", state.selections_text)
                    self.assertNotIn("OPT-B", state.selections_text)
                    active = self._active_requirements(session, request.id)
                    self.assertEqual(len(active), 1)
                    self.assertIn("OPT-A", active[0].approved_entry_key or "")
                    self.assertEqual(active[0].start_date, D1)
                    revision_count = session.scalar(
                        select(func.count(RequestApprovalRevision.id)).where(
                            RequestApprovalRevision.workforce_request_id == request.id
                        )
                    )
                    self.assertEqual(revision_count, 1)
            finally:
                engine.dispose()

            with TestClient(app, raise_server_exceptions=False) as client:
                operational = client.put(
                    f"/api/v1/demands/{number}/lines/{line_id}/operational-alternative-groups/VISITE/selection",
                    json={
                        "period_id": "OPT-B",
                        "expected_operational_version": 1,
                    },
                )
                self.assertEqual(operational.status_code, 200, operational.text)
                self.assertEqual(operational.json()["operational_version"], 2)

                stale = client.put(
                    f"/api/v1/demands/{number}/lines/{line_id}/operational-alternative-groups/VISITE/selection",
                    json={
                        "period_id": "OPT-A",
                        "expected_operational_version": 1,
                    },
                )
                self.assertEqual(stale.status_code, 409, stale.text)
                self.assertEqual(
                    stale.json()["error"]["code"],
                    "operational_choice_version_conflict",
                )

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
                    state = session.get(RequestOperationalState, request.id)
                    assert state is not None
                    self.assertEqual(state.version, 2)
                    self.assertIn("OPT-B", state.selections_text)
                    active = self._active_requirements(session, request.id)
                    self.assertEqual(len(active), 1)
                    self.assertIn("OPT-B", active[0].approved_entry_key or "")
                    # The candidate OPT-B now lives on D4, but the active plan must
                    # still use the immutable approved OPT-B window (D2).
                    self.assertEqual(active[0].start_date, D2)
                    self.assertEqual(active[0].end_date, D2)
                    self.assertEqual(active[0].priority, "Normale")
                    revision_count = session.scalar(
                        select(func.count(RequestApprovalRevision.id)).where(
                            RequestApprovalRevision.workforce_request_id == request.id
                        )
                    )
                    self.assertEqual(revision_count, 1)
            finally:
                engine.dispose()

    def test_operational_confirmation_changes_inheritance_without_reapproval(self) -> None:
        with TemporaryDirectory() as directory:
            database_url = self._database(directory)
            app = create_api_app(
                database_url,
                actor_name="coord-confirm",
                auth_resolver=TEST_ADMIN_AUTH_RESOLVER,
            )
            with TestClient(app, raise_server_exceptions=False) as client:
                number, line_id = self._create_line(
                    client,
                    confirmation="Tentative",
                )
                submitted = client.post(f"/api/v1/demands/{number}/submit")
                self.assertEqual(submitted.status_code, 200, submitted.text)
                approved = client.post(
                    f"/api/v1/demands/{number}/approve",
                    json={"comment": "Approbation confirmation"},
                )
                self.assertEqual(approved.status_code, 200, approved.text)

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
                    revision_count = session.scalar(
                        select(func.count(RequestApprovalRevision.id)).where(
                            RequestApprovalRevision.workforce_request_id == request.id
                        )
                    )
                    self.assertEqual(revision_count, 1)
                    state = session.get(RequestOperationalState, request.id)
                    assert state is not None
                    self.assertEqual(state.version, 1)
                    active = self._active_requirements(session, request.id)
                    self.assertEqual(len(active), 1)
                    self.assertEqual(active[0].confirmation, "Tentative")
                    self.assertFalse(active[0].confirmation_overridden)
            finally:
                engine.dispose()

            with TestClient(app, raise_server_exceptions=False) as client:
                confirmed = client.put(
                    f"/api/v1/demands/{number}/lines/{line_id}/operational-confirmation",
                    json={
                        "confirmation": "Confirmée",
                        "expected_operational_version": 1,
                    },
                )
                self.assertEqual(confirmed.status_code, 200, confirmed.text)
                self.assertEqual(confirmed.json()["operational_version"], 2)

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
                    self.assertEqual(request.status, "En planification")
                    active = self._active_requirements(session, request.id)
                    self.assertEqual(len(active), 1)
                    self.assertEqual(active[0].confirmation, "Confirmée")
                    self.assertFalse(active[0].confirmation_overridden)
                    revision_count = session.scalar(
                        select(func.count(RequestApprovalRevision.id)).where(
                            RequestApprovalRevision.workforce_request_id == request.id
                        )
                    )
                    self.assertEqual(revision_count, 1)
                    state = session.get(RequestOperationalState, request.id)
                    assert state is not None
                    self.assertEqual(state.version, 2)
                    confirmations = json.loads(state.confirmations_text)
                    self.assertEqual(
                        next(iter(confirmations.values())),
                        "Confirmée",
                    )
            finally:
                engine.dispose()


if __name__ == "__main__":
    unittest.main()
