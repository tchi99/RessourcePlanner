from __future__ import annotations

from datetime import date
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.application.errors import ApplicationConflictError
from app.application.security import AuthPrincipal, ROLE_ADMIN
from app.infrastructure.sql import (
    AppUser,
    Asset,
    AssetAllocation,
    AssetRequirement,
    AssetType,
    Base,
    PlanningMutationState,
    Project,
    RequestLine,
    Resource,
    ResourceRequirement,
    Shift,
    SqlDemandRepository,
    SqlPlannerQueryRepository,
    WorkforceRequest,
    WorkforceRequestHistory,
    create_session_factory,
    create_sql_engine,
)
from app.server import create_api_app
from app.server.security import static_auth_resolver


DAY = date(2026, 9, 23)

TEST_CANCELLATION_ADMIN_AUTH_RESOLVER = static_auth_resolver(
    AuthPrincipal.from_roles(
        local_user_id="U-ADMIN",
        issuer="urn:resourceplanner:test",
        subject="cancellation-admin",
        display_name="Coordonnateur annulation",
        email=None,
        roles=(ROLE_ADMIN,),
        auth_mode="test",
    )
)


class DemandCancellationRequestTests(unittest.TestCase):
    @staticmethod
    def _database(directory: str) -> str:
        path = Path(directory) / "cancellation-request.db"
        url = f"sqlite+pysqlite:///{path.as_posix()}"
        engine = create_sql_engine(url)
        Base.metadata.create_all(engine)
        factory = create_session_factory(engine)
        with factory.begin() as session:
            session.add_all(
                [
                    AppUser(
                        id="U-ADMIN",
                        issuer="urn:resourceplanner:test",
                        subject="cancellation-admin",
                        display_name="Coordonnateur annulation",
                        roles_json='["ADMIN"]',
                        active=True,
                    ),
                    Project(id="P1", number="P-1", name="Projet annulation"),
                    Resource(id="R1", name="Alice", active=True),
                    AssetType(
                        id="AT1",
                        code="VEH",
                        label="Véhicule",
                        category="VEHICLE",
                    ),
                ]
            )
            session.flush()
            session.add(Asset(id="A1", code="TRUCK-1", label="Camion 1", asset_type_id="AT1"))
            session.add_all(
                [
                    WorkforceRequest(
                        id="D-HUMAN",
                        legacy_demand_number="DMO-CANCEL-HUMAN",
                        project_id="P1",
                        status="En planification",
                        aggregate_version=4,
                        line_mode=True,
                    ),
                    WorkforceRequest(
                        id="D-ASSET",
                        legacy_demand_number="DMO-CANCEL-ASSET",
                        project_id="P1",
                        status="En planification",
                        aggregate_version=2,
                        line_mode=True,
                    ),
                    WorkforceRequest(
                        id="D-EMPTY",
                        legacy_demand_number="DMO-CANCEL-EMPTY",
                        project_id="P1",
                        status="En planification",
                        aggregate_version=3,
                        line_mode=True,
                    ),
                ]
            )
            session.flush()
            session.add_all(
                [
                    RequestLine(
                        id="L-HUMAN",
                        workforce_request_id="D-HUMAN",
                        position=0,
                        kind="WORKFORCE",
                        desired_start=DAY,
                        desired_end=DAY,
                        estimated_hours=8,
                    ),
                    RequestLine(
                        id="L-ASSET",
                        workforce_request_id="D-ASSET",
                        position=0,
                        kind="ASSET",
                        desired_start=DAY,
                        desired_end=DAY,
                        estimated_hours=8,
                        asset_type_id="AT1",
                    ),
                    RequestLine(
                        id="L-EMPTY",
                        workforce_request_id="D-EMPTY",
                        position=0,
                        kind="WORKFORCE",
                        desired_start=DAY,
                        desired_end=DAY,
                        estimated_hours=8,
                    ),
                ]
            )
            session.flush()
            session.add_all(
                [
                    ResourceRequirement(
                        id="REQ-HUMAN",
                        legacy_segment_id="SEG-HUMAN",
                        project_id="P1",
                        workforce_request_id="D-HUMAN",
                        source_request_line_id="L-HUMAN",
                        start_date=DAY,
                        end_date=DAY,
                        planned_hours=8,
                        status="Planifié",
                        origin="REQUEST",
                    ),
                    ResourceRequirement(
                        id="REQ-EMPTY",
                        legacy_segment_id="SEG-EMPTY",
                        project_id="P1",
                        workforce_request_id="D-EMPTY",
                        source_request_line_id="L-EMPTY",
                        start_date=DAY,
                        end_date=DAY,
                        planned_hours=8,
                        status="Planifié",
                        origin="REQUEST",
                    ),
                    AssetRequirement(
                        id="AREQ-1",
                        project_id="P1",
                        workforce_request_id="D-ASSET",
                        source_request_line_id="L-ASSET",
                        approved_entry_key="LINE:L-ASSET",
                        slot_index=0,
                        asset_type_id="AT1",
                        start_date=DAY,
                        end_date=DAY,
                        usage_hours=8,
                        status="Planifié",
                    ),
                ]
            )
            session.flush()
            session.add_all(
                [
                    Shift(
                        id="SHIFT-HUMAN",
                        resource_requirement_id="REQ-HUMAN",
                        resource_id="R1",
                        work_date=DAY,
                        hours=8,
                        source="MANUAL",
                        locked=True,
                    ),
                    AssetAllocation(
                        id="ALLOC-ASSET",
                        asset_requirement_id="AREQ-1",
                        asset_id="A1",
                        start_date=DAY,
                        end_date=DAY,
                        locked=True,
                        source="MANUAL",
                    ),
                    PlanningMutationState(id="GLOBAL", version=9),
                ]
            )
        engine.dispose()
        return url

    @staticmethod
    def _row(database_url: str, number: str) -> tuple[WorkforceRequest, int, int]:
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
                planning_version = session.scalar(
                    select(PlanningMutationState.version).where(
                        PlanningMutationState.id == "GLOBAL"
                    )
                )
                shift_count = session.scalar(select(func.count()).select_from(Shift))
                session.expunge(request)
                return request, int(planning_version or 0), int(shift_count or 0)
        finally:
            engine.dispose()

    def test_real_materialization_distinguishes_human_asset_and_requirement_only(self) -> None:
        with TemporaryDirectory() as directory:
            database_url = self._database(directory)
            engine = create_sql_engine(database_url)
            factory = create_session_factory(engine)
            try:
                with factory() as session:
                    rows = SqlPlannerQueryRepository(
                        session
                    ).list_demand_cancellation_materializations(
                        (
                            "DMO-CANCEL-HUMAN",
                            "DMO-CANCEL-ASSET",
                            "DMO-CANCEL-EMPTY",
                        )
                    )
                    by_number = {row.demand_number: row for row in rows}

                    human = by_number["DMO-CANCEL-HUMAN"]
                    self.assertEqual(human.human_shift_count, 1)
                    self.assertEqual(human.locked_human_shift_count, 1)
                    self.assertTrue(human.has_operational_decisions)

                    asset = by_number["DMO-CANCEL-ASSET"]
                    self.assertEqual(asset.asset_allocation_count, 1)
                    self.assertEqual(asset.locked_asset_allocation_count, 1)
                    self.assertTrue(asset.has_operational_decisions)

                    empty = by_number["DMO-CANCEL-EMPTY"]
                    self.assertEqual(empty.human_shift_count, 0)
                    self.assertEqual(empty.asset_allocation_count, 0)
                    self.assertFalse(empty.has_operational_decisions)
            finally:
                engine.dispose()

    def test_detail_workflow_and_list_share_the_same_materialized_policy(self) -> None:
        with TemporaryDirectory() as directory:
            database_url = self._database(directory)
            app = create_api_app(
                database_url,
                auth_resolver=TEST_CANCELLATION_ADMIN_AUTH_RESOLVER,
            )
            with TestClient(app, raise_server_exceptions=False) as client:
                listed = client.get("/api/v1/demands")
                workflow = client.get(
                    "/api/v1/demands/DMO-CANCEL-HUMAN/workflow-actions"
                )
                detail = client.get(
                    "/api/v1/demands/DMO-CANCEL-HUMAN/detail"
                )

            self.assertEqual(listed.status_code, 200, listed.text)
            self.assertEqual(workflow.status_code, 200, workflow.text)
            self.assertEqual(detail.status_code, 200, detail.text)

            listed_human = next(
                row
                for row in listed.json()
                if row["number"] == "DMO-CANCEL-HUMAN"
            )
            listed_empty = next(
                row
                for row in listed.json()
                if row["number"] == "DMO-CANCEL-EMPTY"
            )
            workflow_policy = workflow.json()["cancellation"]
            detail_body = detail.json()

            self.assertEqual(
                listed_human["cancellation_policy"],
                workflow_policy,
            )
            self.assertEqual(
                detail_body["demand"]["cancellation_policy"],
                workflow_policy,
            )
            self.assertEqual(
                detail_body["workflow"]["cancellation"],
                workflow_policy,
            )
            self.assertTrue(workflow_policy["has_operational_decisions"])
            self.assertFalse(workflow_policy["direct_cancel"])
            self.assertTrue(workflow_policy["request_cancellation"])
            self.assertIn(
                "request-cancellation",
                workflow.json()["available_actions"],
            )
            self.assertNotIn("cancel", workflow.json()["available_actions"])
            self.assertTrue(listed_empty["cancellation_policy"]["direct_cancel"])
            self.assertFalse(
                listed_empty["cancellation_policy"]["request_cancellation"]
            )

    def test_request_reject_and_successive_cycle_keep_plan_untouched(self) -> None:
        with TemporaryDirectory() as directory:
            database_url = self._database(directory)
            app = create_api_app(
                database_url,
                auth_resolver=TEST_CANCELLATION_ADMIN_AUTH_RESOLVER,
            )

            before, planning_before, shifts_before = self._row(
                database_url,
                "DMO-CANCEL-HUMAN",
            )
            self.assertEqual(before.aggregate_version, 4)
            self.assertEqual(planning_before, 9)

            with TestClient(app, raise_server_exceptions=False) as client:
                direct = client.post(
                    "/api/v1/demands/DMO-CANCEL-HUMAN/cancel",
                    json={"expected_version": 4},
                )
                self.assertEqual(direct.status_code, 409, direct.text)
                self.assertEqual(
                    direct.json()["error"]["code"],
                    "active_operational_decisions",
                )

                missing_reason = client.post(
                    "/api/v1/demands/DMO-CANCEL-HUMAN/request-cancellation",
                    json={"reason": "   ", "expected_version": 4},
                )
                self.assertEqual(missing_reason.status_code, 422, missing_reason.text)
                self.assertEqual(
                    missing_reason.json()["error"]["code"],
                    "cancellation_reason_required",
                )

                requested = client.post(
                    "/api/v1/demands/DMO-CANCEL-HUMAN/request-cancellation",
                    json={
                        "reason": "Le mandat est abandonné",
                        "expected_version": 4,
                    },
                )
                self.assertEqual(requested.status_code, 200, requested.text)
                first_cycle = requested.json()["cancellation_request_id"]
                UUID(first_cycle)
                self.assertEqual(requested.json()["status"], "En planification")
                self.assertEqual(requested.json()["cancellation_state"], "PENDING")

                stale = client.post(
                    "/api/v1/demands/DMO-CANCEL-HUMAN/request-cancellation",
                    json={
                        "reason": "Tentative obsolète",
                        "expected_version": 4,
                    },
                )
                self.assertEqual(stale.status_code, 409, stale.text)
                self.assertEqual(
                    stale.json()["error"]["code"],
                    "demand_version_conflict",
                )

                rejected = client.post(
                    "/api/v1/demands/DMO-CANCEL-HUMAN/reject-cancellation",
                    json={
                        "cancellation_request_id": first_cycle,
                        "comment": "Le plan doit être conservé",
                        "expected_version": 5,
                    },
                )
                self.assertEqual(rejected.status_code, 200, rejected.text)
                self.assertEqual(rejected.json()["cancellation_state"], "REJECTED")

                requested_again = client.post(
                    "/api/v1/demands/DMO-CANCEL-HUMAN/request-cancellation",
                    json={
                        "reason": "Nouvelle demande après discussion",
                        "expected_version": 6,
                    },
                )
                self.assertEqual(requested_again.status_code, 200, requested_again.text)
                second_cycle = requested_again.json()["cancellation_request_id"]
                UUID(second_cycle)
                self.assertNotEqual(first_cycle, second_cycle)

            after, planning_after, shifts_after = self._row(
                database_url,
                "DMO-CANCEL-HUMAN",
            )
            self.assertEqual(after.status, "En planification")
            self.assertEqual(after.aggregate_version, 7)
            self.assertEqual(after.cancellation_state, "PENDING")
            self.assertEqual(after.cancellation_request_id, second_cycle)
            self.assertEqual(after.cancellation_requested_by_user_id, "U-ADMIN")
            self.assertEqual(
                after.cancellation_reason,
                "Nouvelle demande après discussion",
            )
            self.assertIsNone(after.cancellation_resolved_at)
            self.assertIsNone(after.cancellation_resolution_comment)
            self.assertEqual(planning_after, planning_before)
            self.assertEqual(shifts_after, shifts_before)

            engine = create_sql_engine(database_url)
            factory = create_session_factory(engine)
            try:
                with factory() as session:
                    history = tuple(
                        session.scalars(
                            select(WorkforceRequestHistory)
                            .where(
                                WorkforceRequestHistory.workforce_request_id
                                == "D-HUMAN"
                            )
                            .order_by(
                                WorkforceRequestHistory.occurred_at,
                                WorkforceRequestHistory.id,
                            )
                        ).all()
                    )
                    cancellation_events = tuple(
                        row
                        for row in history
                        if row.action
                        in {"Demande d'annulation", "Refus d'annulation"}
                    )
                    self.assertEqual(
                        [row.action for row in cancellation_events],
                        [
                            "Demande d'annulation",
                            "Refus d'annulation",
                            "Demande d'annulation",
                        ],
                    )
                    first_details = json.loads(cancellation_events[0].details or "{}")
                    reject_details = json.loads(cancellation_events[1].details or "{}")
                    second_details = json.loads(cancellation_events[2].details or "{}")
                    self.assertEqual(
                        first_details["cancellation_request_id"],
                        first_cycle,
                    )
                    self.assertEqual(
                        reject_details["cancellation_request_id"],
                        first_cycle,
                    )
                    self.assertEqual(reject_details["resolution"], "REJECTED")
                    self.assertEqual(
                        second_details["cancellation_request_id"],
                        second_cycle,
                    )
                    self.assertEqual(
                        second_details["reason"],
                        "Nouvelle demande après discussion",
                    )
            finally:
                engine.dispose()

    def test_repository_cas_rejects_stale_request_without_partial_write(self) -> None:
        with TemporaryDirectory() as directory:
            database_url = self._database(directory)
            engine = create_sql_engine(database_url)
            factory = create_session_factory(engine)
            try:
                with factory.begin() as session:
                    request = session.get(WorkforceRequest, "D-HUMAN")
                    assert request is not None
                    request.aggregate_version = 5

                with self.assertRaises(ApplicationConflictError) as raised:
                    with factory.begin() as session:
                        SqlDemandRepository(
                            session,
                            actor_name="Coordonnateur",
                        ).request_cancellation(
                            "DMO-CANCEL-HUMAN",
                            cancellation_request_id=(
                                "11111111-1111-1111-1111-111111111111"
                            ),
                            reason="Stale",
                            expected_version=4,
                        )
                self.assertEqual(raised.exception.code, "demand_version_conflict")

                with factory() as session:
                    request = session.get(WorkforceRequest, "D-HUMAN")
                    assert request is not None
                    self.assertEqual(request.aggregate_version, 5)
                    self.assertIsNone(request.cancellation_state)
                    self.assertIsNone(request.cancellation_request_id)
                    audit_count = session.scalar(
                        select(func.count())
                        .select_from(WorkforceRequestHistory)
                        .where(
                            WorkforceRequestHistory.workforce_request_id
                            == "D-HUMAN",
                            WorkforceRequestHistory.action
                            == "Demande d'annulation",
                        )
                    )
                    self.assertEqual(int(audit_count or 0), 0)
            finally:
                engine.dispose()


if __name__ == "__main__":
    unittest.main()
