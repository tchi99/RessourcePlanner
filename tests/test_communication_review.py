from __future__ import annotations

import unittest
from datetime import date

from app.domain.communication_planning import CommunicationBatch, CommunicationDraft
from app.domain.communication_review import (
    DraftReview,
    apply_manual_review,
    stale_prepared_batch,
)


WEEK = date(2026, 8, 24)


def draft(recipient_id: str, subject: str = "Sujet", body: str = "Corps") -> CommunicationDraft:
    return CommunicationDraft(
        audience="technician",
        recipient_id=recipient_id,
        recipient_email=f"{recipient_id}@invalid.test",
        subject=subject,
        body=body,
        message_kind="weekly_plan",
        week_start=WEEK,
        snapshot_fingerprint="planning-1",
    )


class CommunicationReviewTests(unittest.TestCase):
    def test_coordinator_can_edit_subject_and_body(self) -> None:
        batch = CommunicationBatch((draft("tech-a"),), (), "planning-1")
        reviewed = apply_manual_review(
            batch,
            {("technician", "tech-a"): DraftReview(subject="Sujet ajusté", body="Corps ajusté")},
        )
        self.assertEqual(reviewed.drafts[0].subject, "Sujet ajusté")
        self.assertEqual(reviewed.drafts[0].body, "Corps ajusté")
        self.assertTrue(reviewed.drafts[0].requires_manual_approval)
        self.assertEqual(reviewed.snapshot_fingerprint, "planning-1")

    def test_coordinator_can_exclude_one_recipient(self) -> None:
        batch = CommunicationBatch((draft("tech-a"), draft("tech-b")), (), "planning-1")
        reviewed = apply_manual_review(
            batch,
            {("technician", "tech-b"): DraftReview(include=False)},
        )
        self.assertEqual([row.recipient_id for row in reviewed.drafts], ["tech-a"])

    def test_blank_subject_or_body_is_rejected_for_included_message(self) -> None:
        batch = CommunicationBatch((draft("tech-a"),), (), "planning-1")
        with self.assertRaises(ValueError):
            apply_manual_review(
                batch,
                {("technician", "tech-a"): DraftReview(subject="")},
            )
        with self.assertRaises(ValueError):
            apply_manual_review(
                batch,
                {("technician", "tech-a"): DraftReview(body="")},
            )

    def test_stale_batch_only_when_both_fingerprints_exist_and_differ(self) -> None:
        self.assertTrue(stale_prepared_batch("old", "new"))
        self.assertFalse(stale_prepared_batch("same", "same"))
        self.assertFalse(stale_prepared_batch("", "new"))
        self.assertFalse(stale_prepared_batch("old", ""))


if __name__ == "__main__":
    unittest.main()
