from __future__ import annotations

import unittest
from datetime import date, datetime

from app.domain.communication_audit import (
    CommunicationAuditState,
    STATUS_APPROVED,
    STATUS_DRAFTS_CREATED,
    STATUS_OBSOLETE,
    approve_batch,
    is_stale_open_batch,
    mark_drafts_created,
    mark_obsolete,
)
from app.domain.communication_transport import (
    MESSAGE_STATUS_DRAFT_CREATED,
    all_message_drafts_created,
    draft_created_message_ids,
    pending_draft_message_ids,
)


WEEK = date(2026, 8, 24)
NOW = datetime(2026, 8, 20, 12, 0)


def approved_state() -> CommunicationAuditState:
    prepared = CommunicationAuditState(
        batch_id="BATCH-TRANSPORT",
        week_start=WEEK,
        message_kind="weekly_plan",
        snapshot_fingerprint="fp-1",
        prepared_by="coord",
        prepared_at=NOW,
    )
    return approve_batch(prepared, approved_by="coord", approved_at=NOW)


class CommunicationTransportTests(unittest.TestCase):
    def test_approved_batch_advances_to_drafts_created(self) -> None:
        state = mark_drafts_created(approved_state())
        self.assertEqual(state.status, STATUS_DRAFTS_CREATED)
        self.assertEqual(state.approved_by, "coord")

    def test_unapproved_batch_cannot_create_drafts_state(self) -> None:
        state = CommunicationAuditState(
            batch_id="B",
            week_start=WEEK,
            message_kind="weekly_plan",
            snapshot_fingerprint="fp",
        )
        with self.assertRaises(ValueError):
            mark_drafts_created(state)

    def test_drafts_created_batch_is_not_auto_obsoleted_by_fingerprint_change(self) -> None:
        state = mark_drafts_created(approved_state())
        self.assertFalse(
            is_stale_open_batch(state.status, state.snapshot_fingerprint, "fp-2")
        )
        self.assertEqual(mark_obsolete(state).status, STATUS_OBSOLETE)

    def test_message_policy_separates_pending_and_created_drafts(self) -> None:
        rows = [
            {"IDMessage": "M1", "Statut": STATUS_APPROVED},
            {"IDMessage": "M2", "Statut": MESSAGE_STATUS_DRAFT_CREATED},
        ]
        self.assertEqual(pending_draft_message_ids(rows), ("M1",))
        self.assertEqual(draft_created_message_ids(rows), ("M2",))
        self.assertFalse(all_message_drafts_created(rows))

    def test_all_message_drafts_created_requires_nonempty_complete_batch(self) -> None:
        self.assertFalse(all_message_drafts_created([]))
        self.assertTrue(
            all_message_drafts_created(
                [
                    {"IDMessage": "M1", "Statut": MESSAGE_STATUS_DRAFT_CREATED},
                    {"IDMessage": "M2", "Statut": MESSAGE_STATUS_DRAFT_CREATED},
                ]
            )
        )


if __name__ == "__main__":
    unittest.main()
