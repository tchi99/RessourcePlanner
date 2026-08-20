from __future__ import annotations

import unittest
from datetime import date, datetime

from app.domain.communication_audit import (
    CommunicationAuditState,
    STATUS_APPROVED,
    STATUS_CANCELLED,
    STATUS_COMMUNICATED,
    approve_batch,
    cancel_batch,
    is_duplicate_communicated_snapshot,
    mark_communicated,
)


WEEK = date(2026, 8, 24)
NOW = datetime(2026, 8, 20, 8, 30)


def prepared() -> CommunicationAuditState:
    return CommunicationAuditState(
        batch_id="BATCH-1",
        week_start=WEEK,
        message_kind="weekly_plan",
        snapshot_fingerprint="abc123",
        prepared_by="coord",
        prepared_at=NOW,
    )


class CommunicationAuditTests(unittest.TestCase):
    def test_approval_requires_coordinator_identity(self) -> None:
        with self.assertRaises(ValueError):
            approve_batch(prepared(), approved_by="", approved_at=NOW)

    def test_prepared_batch_can_be_approved_then_communicated(self) -> None:
        approved = approve_batch(prepared(), approved_by="coord", approved_at=NOW)
        self.assertEqual(approved.status, STATUS_APPROVED)
        self.assertEqual(approved.approved_by, "coord")

        communicated = mark_communicated(approved, communicated_at=NOW)
        self.assertEqual(communicated.status, STATUS_COMMUNICATED)
        self.assertEqual(communicated.approved_by, "coord")

    def test_unapproved_batch_cannot_be_marked_communicated(self) -> None:
        with self.assertRaises(ValueError):
            mark_communicated(prepared(), communicated_at=NOW)

    def test_communicated_batch_cannot_be_cancelled(self) -> None:
        state = mark_communicated(
            approve_batch(prepared(), approved_by="coord", approved_at=NOW),
            communicated_at=NOW,
        )
        with self.assertRaises(ValueError):
            cancel_batch(state)

    def test_prepared_batch_can_be_cancelled(self) -> None:
        self.assertEqual(cancel_batch(prepared()).status, STATUS_CANCELLED)

    def test_duplicate_detection_only_uses_communicated_same_week_and_kind(self) -> None:
        communicated = mark_communicated(
            approve_batch(prepared(), approved_by="coord", approved_at=NOW),
            communicated_at=NOW,
        )
        self.assertTrue(
            is_duplicate_communicated_snapshot(
                "abc123", [communicated], week_start=WEEK, message_kind="weekly_plan"
            )
        )
        self.assertFalse(
            is_duplicate_communicated_snapshot(
                "abc123", [communicated], week_start=date(2026, 8, 31), message_kind="weekly_plan"
            )
        )
        self.assertFalse(
            is_duplicate_communicated_snapshot(
                "abc123", [communicated], week_start=WEEK, message_kind="planning_change"
            )
        )


if __name__ == "__main__":
    unittest.main()
