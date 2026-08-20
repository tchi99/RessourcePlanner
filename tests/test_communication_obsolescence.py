from __future__ import annotations

import unittest
from datetime import date, datetime

from app.domain.communication_audit import (
    CommunicationAuditState,
    STATUS_APPROVED,
    STATUS_COMMUNICATED,
    STATUS_OBSOLETE,
    STATUS_PREPARED,
    is_stale_open_batch,
    mark_obsolete,
)


class CommunicationObsolescenceTests(unittest.TestCase):
    def state(self, status: str) -> CommunicationAuditState:
        return CommunicationAuditState(
            batch_id="batch-demo",
            week_start=date(2026, 8, 24),
            message_kind="weekly_plan",
            snapshot_fingerprint="old",
            status=status,
            prepared_by="coord",
            prepared_at=datetime(2026, 8, 20, 10, 0),
            approved_by="coord" if status == STATUS_APPROVED else "",
            approved_at=datetime(2026, 8, 20, 10, 5) if status == STATUS_APPROVED else None,
        )

    def test_prepared_batch_is_stale_when_fingerprint_changes(self) -> None:
        self.assertTrue(is_stale_open_batch(STATUS_PREPARED, "old", "new"))

    def test_approved_batch_is_stale_when_fingerprint_changes(self) -> None:
        self.assertTrue(is_stale_open_batch(STATUS_APPROVED, "old", "new"))

    def test_same_fingerprint_is_not_stale(self) -> None:
        self.assertFalse(is_stale_open_batch(STATUS_APPROVED, "same", "same"))

    def test_communicated_batch_is_never_retroactively_obsoleted(self) -> None:
        self.assertFalse(is_stale_open_batch(STATUS_COMMUNICATED, "old", "new"))
        with self.assertRaises(ValueError):
            mark_obsolete(self.state(STATUS_COMMUNICATED))

    def test_mark_obsolete_preserves_approval_audit(self) -> None:
        before = self.state(STATUS_APPROVED)
        after = mark_obsolete(before)
        self.assertEqual(after.status, STATUS_OBSOLETE)
        self.assertEqual(after.approved_by, before.approved_by)
        self.assertEqual(after.approved_at, before.approved_at)


if __name__ == "__main__":
    unittest.main()
