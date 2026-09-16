from __future__ import annotations

from datetime import date
from decimal import Decimal
import unittest

from app.application.communications import (
    KIND_CHANGE,
    KIND_WEEKLY,
    STATUS_APPROVED,
    STATUS_COMMUNICATED,
    STATUS_PREPARED,
    CommunicationReviewInput,
    CommunicationService,
)
from app.infrastructure.sql import (
    Base,
    Project,
    Resource,
    ResourceRequirement,
    Shift,
    create_session_factory,
    create_sql_engine,
    transactional_session,
)
from app.infrastructure.sql.communication_repository import SqlCommunicationRepository


WEEK = date(2026, 9, 21)


class SqlCommunicationWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_sql_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.factory = create_session_factory(self.engine)
        with transactional_session(self.factory) as session:
            session.add_all(
                [
                    Project(id="P1", number="P-100", name="Projet test", status="Actif"),
                    Resource(
                        id="R1",
                        external_id="EMP-1",
                        name="Technicien test",
                        email="tech" + chr(64) + "example.test",
                        active=True,
                    ),
                ]
            )
            session.flush()
            session.add(
                ResourceRequirement(
                    id="REQ1",
                    legacy_segment_id="SEG-1",
                    project_id="P1",
                    workforce_request_id=None,
                    assigned_resource_id="R1",
                    start_date=WEEK,
                    end_date=WEEK,
                    planned_hours=Decimal("8"),
                    status="Planifié",
                    planning_type="Flexible",
                    priority="Normale",
                    origin="AD_HOC",
                    confirmation="Confirmée",
                )
            )
            session.flush()
            session.add(
                Shift(
                    id="S1",
                    resource_requirement_id="REQ1",
                    resource_id="R1",
                    work_date=WEEK,
                    hours=Decimal("8"),
                    source="MANUAL",
                    locked=True,
                )
            )

    def tearDown(self) -> None:
        self.engine.dispose()

    def _service(self, session) -> CommunicationService:
        return CommunicationService(SqlCommunicationRepository(session))

    def test_prepare_approve_communicate_then_build_delta(self) -> None:
        with transactional_session(self.factory) as session:
            service = self._service(session)
            preview = service.preview(week_start=WEEK)
            self.assertEqual(preview.mode, KIND_WEEKLY)
            self.assertEqual(len(preview.drafts), 1)
            self.assertEqual(preview.missing_contact_ids, ())

            prepared = service.prepare(
                week_start=WEEK,
                expected_fingerprint=preview.snapshot_fingerprint,
                reviews=(
                    CommunicationReviewInput(
                        audience=preview.drafts[0].audience,
                        recipient_id=preview.drafts[0].recipient_id,
                        subject="Objet révisé",
                        body="Message révisé",
                    ),
                ),
                actor_name="Coordonnateur",
            )
            self.assertEqual(prepared.status, STATUS_PREPARED)
            self.assertEqual(prepared.messages[0].subject, "Objet révisé")

            approved = service.approve(batch_id=prepared.id, actor_name="Coordonnateur")
            self.assertEqual(approved.status, STATUS_APPROVED)
            communicated = service.mark_communicated(
                batch_id=prepared.id,
                actor_name="Coordonnateur",
            )
            self.assertEqual(communicated.status, STATUS_COMMUNICATED)

            unchanged = service.preview(week_start=WEEK)
            self.assertEqual(unchanged.mode, KIND_CHANGE)
            self.assertEqual(unchanged.drafts, ())

            shift = session.get(Shift, "S1")
            assert shift is not None
            shift.hours = Decimal("6")
            session.flush()

            changed = service.preview(week_start=WEEK)
            self.assertEqual(changed.mode, KIND_CHANGE)
            self.assertEqual(len(changed.drafts), 1)
            self.assertIn("MODIFICATION", changed.drafts[0].body)

    def test_excluded_message_is_journaled_but_not_counted_as_included(self) -> None:
        with transactional_session(self.factory) as session:
            service = self._service(session)
            preview = service.preview(week_start=WEEK)
            with self.assertRaisesRegex(Exception, "Au moins un message"):
                service.prepare(
                    week_start=WEEK,
                    expected_fingerprint=preview.snapshot_fingerprint,
                    reviews=(
                        CommunicationReviewInput(
                            audience=preview.drafts[0].audience,
                            recipient_id=preview.drafts[0].recipient_id,
                            include=False,
                        ),
                    ),
                    actor_name="Coordonnateur",
                )

    def test_prepared_batch_becomes_stale_when_planning_changes(self) -> None:
        with transactional_session(self.factory) as session:
            service = self._service(session)
            preview = service.preview(week_start=WEEK)
            prepared = service.prepare(
                week_start=WEEK,
                expected_fingerprint=preview.snapshot_fingerprint,
                reviews=(),
                actor_name="Coordonnateur",
            )
            shift = session.get(Shift, "S1")
            assert shift is not None
            shift.hours = Decimal("7")
            session.flush()
            rows = service.list_batches(week_start=WEEK)
            self.assertEqual(rows[0].id, prepared.id)
            self.assertTrue(rows[0].stale)
            with self.assertRaisesRegex(Exception, "planning a changé"):
                service.approve(batch_id=prepared.id, actor_name="Coordonnateur")


if __name__ == "__main__":
    unittest.main()
