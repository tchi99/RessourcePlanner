from __future__ import annotations

from datetime import date, time, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.infrastructure.sql import (
    Base,
    ORIGIN_AD_HOC,
    PlanningChangeHistory,
    Project,
    Resource,
    ResourceAvailabilityRule,
    ResourceRequirement,
    Shift,
    create_session_factory,
    create_sql_engine,
)
from app.server import create_api_app
from tests.http_test_auth import TEST_ADMIN_AUTH_RESOLVER


DAY = date(2026, 9, 22)
NEXT_DAY = DAY + timedelta(days=1)


class PlanningDropWindowExtensionTests(unittest.TestCase):
    @staticmethod
    def _database(directory: str, *, with_adhoc: bool = True) -> str:
        path = Path(directory) / "planning-drop-333.db"
        url = f"sqlite:///{path.as_posix()}"
        engine = create_sql_engine(url)
        Base.metadata.create_all(engine)
        factory = create_session_factory(engine)
        with factory.begin() as session:
            session.add(Project(id="P1", number="P-1", name="Projet 333"))
            session.add_all(
                [
                    Resource(id="R1", name="Alice", active=True),
                    Resource(id="R2", name="Bob", active=True),
                ]
            )
            session.flush()
            for resource_id in ("R1", "R2"):
                session.add(
                    ResourceAvailabilityRule(
                        id=f"STD-{resource_id}",
                        resource_id=resource_id,
                        availability_type="Horaire standard",
                        weekdays="Lun,Mar,Mer,Jeu,Ven,Sam,Dim",
                        start_time=time(8, 0),
                        end_time=time(20, 0),
                        active=True,
                    )
                )
            if with_adhoc:
                session.add(
                    ResourceRequirement(
                        id="REQ1",
                        legacy_segment_id="SEG-1",
                        project_id="P1",
                        workforce_request_id=None,
                        assigned_resource_id="R1",
                        start_date=DAY,
                        end_date=DAY,
                        planned_hours=8,
                        status="Planifié",
                        planning_type="Flexible",
                        confirmation="Confirmée",
                        origin=ORIGIN_AD_HOC,
                    )
                )
                session.flush()
                session.add(
                    Shift(
                        id="SHIFT-1",
                        legacy_allocation_id="ALLOC-1",
                        resource_requirement_id="REQ1",
                        resource_id="R1",
                        work_date=DAY,
                        hours=8,
                        allocation_type="Flexible",
                        source="MANUAL",
                        locked=True,
                        outside_standard_hours=False,
                        confirmation="Confirmée",
                    )
                )
        engine.dispose()
        return url

    def test_evaluate_drop_is_read_only_and_offers_atomic_extension_for_adhoc(self) -> None:
        with TemporaryDirectory() as directory:
            url = self._database(directory)
            app = create_api_app(url, auth_resolver=TEST_ADMIN_AUTH_RESOLVER)
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.post(
                    "/api/v1/allocations/ALLOC-1/evaluate-drop",
                    json={
                        "resource_id": "R2",
                        "day": NEXT_DAY.isoformat(),
                    },
                )
            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertEqual(payload["authorization_decision"], "NOT_APPLICABLE")
            self.assertEqual(payload["current_window"]["end"], DAY.isoformat())
            self.assertEqual(payload["proposed_window"]["end"], NEXT_DAY.isoformat())
            self.assertEqual(
                [action["code"] for action in payload["actions"]],
                ["EXTEND_AND_MOVE", "CANCEL"],
            )

            engine = create_sql_engine(url)
            factory = create_session_factory(engine)
            with factory() as session:
                requirement = session.get(ResourceRequirement, "REQ1")
                shift = session.get(Shift, "SHIFT-1")
                assert requirement is not None and shift is not None
                self.assertEqual(requirement.end_date, DAY)
                self.assertEqual(shift.work_date, DAY)
                self.assertEqual(shift.resource_id, "R1")
            engine.dispose()

    def test_extend_and_move_is_atomic_idempotent_and_audited(self) -> None:
        with TemporaryDirectory() as directory:
            url = self._database(directory)
            app = create_api_app(url, auth_resolver=TEST_ADMIN_AUTH_RESOLVER)
            body = {
                "resource_id": "R2",
                "day": NEXT_DAY.isoformat(),
                "expected_planning_version": 1,
                "confirm_window_extension": True,
            }
            headers = {"Idempotency-Key": "extend-move-333a"}
            with TestClient(app, raise_server_exceptions=False) as client:
                first = client.post(
                    "/api/v1/allocations/ALLOC-1/extend-and-move",
                    json=body,
                    headers=headers,
                )
                replay = client.post(
                    "/api/v1/allocations/ALLOC-1/extend-and-move",
                    json=body,
                    headers=headers,
                )
            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(replay.json(), first.json())
            self.assertEqual(first.json()["operation"], "EXTEND_AND_MOVE")
            self.assertEqual(first.json()["planning_version"], 2)

            engine = create_sql_engine(url)
            factory = create_session_factory(engine)
            with factory() as session:
                requirement = session.get(ResourceRequirement, "REQ1")
                shift = session.get(Shift, "SHIFT-1")
                assert requirement is not None and shift is not None
                self.assertEqual(requirement.start_date, DAY)
                self.assertEqual(requirement.end_date, NEXT_DAY)
                self.assertEqual(shift.resource_id, "R2")
                self.assertEqual(shift.work_date, NEXT_DAY)
                self.assertTrue(shift.locked)
                self.assertEqual(shift.source, "MANUAL")
                extension_audits = int(
                    session.scalar(
                        select(func.count())
                        .select_from(PlanningChangeHistory)
                        .where(
                            PlanningChangeHistory.action
                            == "Extension atomique de fenêtre"
                        )
                    )
                    or 0
                )
                move_audits = int(
                    session.scalar(
                        select(func.count())
                        .select_from(PlanningChangeHistory)
                        .where(
                            PlanningChangeHistory.action
                            == "Déplacement atomique après extension"
                        )
                    )
                    or 0
                )
                self.assertEqual(extension_audits, 1)
                self.assertEqual(move_audits, 1)
            engine.dispose()

    def test_request_outside_exact_approved_entry_is_proposal_only(self) -> None:
        with TemporaryDirectory() as directory:
            url = self._database(directory, with_adhoc=False)
            app = create_api_app(url, auth_resolver=TEST_ADMIN_AUTH_RESOLVER)
            with TestClient(app, raise_server_exceptions=False) as client:
                created = client.post(
                    "/api/v1/demands",
                    json={
                        "project_number": "P-1",
                        "desired_start": DAY.isoformat(),
                        "desired_end": DAY.isoformat(),
                        "estimated_hours": 8,
                        "proposed_technician": "Alice",
                        "submit": True,
                    },
                )
                self.assertEqual(created.status_code, 201, created.text)
                number = created.json()["demand_number"]
                approved = client.post(
                    f"/api/v1/demands/{number}/approve",
                    json={"comment": "Approbation 333A"},
                )
                self.assertEqual(approved.status_code, 200, approved.text)

            engine = create_sql_engine(url)
            factory = create_session_factory(engine)
            with factory() as session:
                requirement = session.scalar(
                    select(ResourceRequirement).where(
                        ResourceRequirement.workforce_request_id.is_not(None),
                        ResourceRequirement.status != "Annulé",
                    )
                )
                assert requirement is not None
                shift = session.scalar(
                    select(Shift).where(
                        Shift.resource_requirement_id == requirement.id,
                        Shift.allocation_type != "Hors horaire requis",
                    )
                )
                assert shift is not None
                allocation_id = shift.legacy_allocation_id or shift.id
            engine.dispose()

            with TestClient(app, raise_server_exceptions=False) as client:
                evaluated = client.post(
                    f"/api/v1/allocations/{allocation_id}/evaluate-drop",
                    json={
                        "resource_id": "R2",
                        "day": NEXT_DAY.isoformat(),
                    },
                )
            self.assertEqual(evaluated.status_code, 200, evaluated.text)
            payload = evaluated.json()
            self.assertEqual(
                payload["authorization_decision"],
                "WINDOW_EXTENSION_REAPPROVAL_REQUIRED",
            )
            self.assertEqual(
                [action["code"] for action in payload["actions"]],
                ["PROPOSE_WINDOW_EXTENSION", "CANCEL"],
            )
            self.assertIsNotNone(payload["approval_revision_id"])
            self.assertIsNotNone(payload["approved_entry_key"])
            self.assertIsNotNone(payload["request_version"])


if __name__ == "__main__":
    unittest.main()
