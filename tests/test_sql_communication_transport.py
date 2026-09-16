from __future__ import annotations

from datetime import date
from decimal import Decimal
import unittest

from app.application.communications import (
    CommunicationReviewInput,
    CommunicationService,
    CommunicationTransportMessage,
    CommunicationTransportResult,
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
TEST_EMAIL = "tech" + chr(64) + "example.test"


class FakeTransport:
    def __init__(self) -> None:
        self.messages: tuple[CommunicationTransportMessage, ...] = ()

    def create_drafts(self, messages):
        self.messages = tuple(messages)
        return CommunicationTransportResult(
            provider="fake_graph",
            created_count=len(self.messages),
        )


class SqlCommunicationTransportTests(unittest.TestCase):
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
                        email=TEST_EMAIL,
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

    def _approved_batch(self, service: CommunicationService):
        preview = service.preview(week_start=WEEK)
        prepared = service.prepare(
            week_start=WEEK,
            expected_fingerprint=preview.snapshot_fingerprint,
            reviews=(
                CommunicationReviewInput(
                    audience=preview.drafts[0].audience,
                    recipient_id=preview.drafts[0].recipient_id,
                ),
            ),
            actor_name="Coordonnateur",
        )
        return service.approve(batch_id=prepared.id, actor_name="Coordonnateur")

    def test_only_approved_current_batch_can_create_and_audit_drafts_once(self) -> None:
        with transactional_session(self.factory) as session:
            transport = FakeTransport()
            service = CommunicationService(
                SqlCommunicationRepository(session),
                transport=transport,
            )
            approved = self._approved_batch(service)

            created = service.create_drafts(
                batch_id=approved.id,
                actor_name="Coordonnateur M365",
            )

            self.assertEqual(len(transport.messages), 1)
            self.assertEqual(transport.messages[0].recipient_email, TEST_EMAIL)
            self.assertEqual(created.drafts_provider, "fake_graph")
            self.assertEqual(created.drafts_created_count, 1)
            self.assertEqual(created.drafts_created_by, "Coordonnateur M365")
            self.assertIsNotNone(created.drafts_created_at)
            self.assertEqual(created.status, "APPROVED")

            with self.assertRaisesRegex(Exception, "déjà été créés"):
                service.create_drafts(
                    batch_id=approved.id,
                    actor_name="Coordonnateur M365",
                )

    def test_transport_is_not_called_before_explicit_approval(self) -> None:
        with transactional_session(self.factory) as session:
            transport = FakeTransport()
            service = CommunicationService(
                SqlCommunicationRepository(session),
                transport=transport,
            )
            preview = service.preview(week_start=WEEK)
            prepared = service.prepare(
                week_start=WEEK,
                expected_fingerprint=preview.snapshot_fingerprint,
                reviews=(),
                actor_name="Coordonnateur",
            )

            with self.assertRaisesRegex(Exception, "doit être approuvé"):
                service.create_drafts(
                    batch_id=prepared.id,
                    actor_name="Coordonnateur",
                )
            self.assertEqual(transport.messages, ())

    def test_missing_transport_is_reported_only_on_explicit_create_action(self) -> None:
        with transactional_session(self.factory) as session:
            service = CommunicationService(SqlCommunicationRepository(session))
            approved = self._approved_batch(service)

            with self.assertRaisesRegex(Exception, "n'est pas configuré"):
                service.create_drafts(
                    batch_id=approved.id,
                    actor_name="Coordonnateur",
                )


if __name__ == "__main__":
    unittest.main()
