from __future__ import annotations

import unittest
from datetime import date

from app.domain.communication_planning import (
    Contact,
    WeeklyAssignment,
    build_change_notification_batch,
    build_weekly_plan_batch,
    compare_weekly_assignments,
    snapshot_fingerprint,
)


WEEK = date(2026, 8, 24)


def assignment(
    segment_id: str,
    resource_id: str = "tech-a",
    manager_id: str = "pm-a",
    day: date = WEEK,
    hours: float = 8.0,
    *,
    outside: bool = False,
    confirmation: str = "Confirmée",
) -> WeeklyAssignment:
    return WeeklyAssignment(
        segment_id=segment_id,
        resource_id=resource_id,
        project_manager_id=manager_id,
        project_number="P-100",
        project_name="Projet démo",
        day=day,
        hours=hours,
        allocation_type="Flexible",
        outside_schedule=outside,
        confirmation=confirmation,
    )


class CommunicationPlanningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contacts = {
            "tech-a": Contact("tech-a", "Technicien A", "tech-a@example.invalid"),
            "tech-b": Contact("tech-b", "Technicien B", "tech-b@example.invalid"),
            "pm-a": Contact("pm-a", "Chargé A", "pm-a@example.invalid"),
            "pm-b": Contact("pm-b", "Chargé B", "pm-b@example.invalid"),
        }

    def test_fingerprint_is_order_independent(self) -> None:
        rows = [assignment("S-1"), assignment("S-2", day=date(2026, 8, 25))]
        self.assertEqual(snapshot_fingerprint(rows), snapshot_fingerprint(list(reversed(rows))))

    def test_weekly_batch_creates_one_draft_per_technician_and_manager(self) -> None:
        rows = [
            assignment("S-1", "tech-a", "pm-a"),
            assignment("S-2", "tech-a", "pm-a", day=date(2026, 8, 25)),
            assignment("S-3", "tech-b", "pm-b", day=date(2026, 8, 26)),
        ]
        batch = build_weekly_plan_batch(rows, self.contacts, WEEK)

        self.assertEqual(len(batch.drafts), 4)
        self.assertEqual(
            {(draft.audience, draft.recipient_id) for draft in batch.drafts},
            {
                ("technician", "tech-a"),
                ("technician", "tech-b"),
                ("project_manager", "pm-a"),
                ("project_manager", "pm-b"),
            },
        )
        self.assertTrue(all(draft.requires_manual_approval for draft in batch.drafts))
        self.assertTrue(all(draft.message_kind == "weekly_plan" for draft in batch.drafts))

    def test_weekly_batch_never_infers_missing_email(self) -> None:
        contacts = {"pm-a": self.contacts["pm-a"]}
        batch = build_weekly_plan_batch([assignment("S-1")], contacts, WEEK)

        self.assertEqual(len(batch.drafts), 1)
        self.assertEqual(batch.drafts[0].recipient_id, "pm-a")
        self.assertEqual(batch.missing_contact_ids, ("tech-a",))

    def test_compare_detects_added_removed_and_modified_segments(self) -> None:
        previous = [assignment("same"), assignment("removed"), assignment("modified")]
        current = [
            assignment("same"),
            assignment("added"),
            assignment("modified", day=date(2026, 8, 26)),
        ]
        changes = compare_weekly_assignments(previous, current)
        self.assertEqual(
            [(change.segment_id, change.kind) for change in changes],
            [("added", "added"), ("modified", "modified"), ("removed", "removed")],
        )

    def test_change_batch_notifies_only_impacted_people(self) -> None:
        previous = [
            assignment("S-1", "tech-a", "pm-a"),
            assignment("S-2", "tech-b", "pm-b", day=date(2026, 8, 25)),
        ]
        current = [
            assignment("S-1", "tech-a", "pm-a", day=date(2026, 8, 26)),
            assignment("S-2", "tech-b", "pm-b", day=date(2026, 8, 25)),
        ]
        batch = build_change_notification_batch(previous, current, self.contacts, WEEK)
        self.assertEqual(
            {(draft.audience, draft.recipient_id) for draft in batch.drafts},
            {("technician", "tech-a"), ("project_manager", "pm-a")},
        )
        self.assertTrue(all(draft.requires_manual_approval for draft in batch.drafts))
        self.assertTrue(all(draft.message_kind == "planning_change" for draft in batch.drafts))

    def test_reassignment_notifies_old_and_new_technicians(self) -> None:
        previous = [assignment("S-1", "tech-a", "pm-a")]
        current = [assignment("S-1", "tech-b", "pm-a")]
        batch = build_change_notification_batch(previous, current, self.contacts, WEEK)

        technicians = {
            draft.recipient_id for draft in batch.drafts if draft.audience == "technician"
        }
        managers = {
            draft.recipient_id for draft in batch.drafts if draft.audience == "project_manager"
        }
        self.assertEqual(technicians, {"tech-a", "tech-b"})
        self.assertEqual(managers, {"pm-a"})

    def test_manager_change_notifies_old_and_new_managers(self) -> None:
        previous = [assignment("S-1", "tech-a", "pm-a")]
        current = [assignment("S-1", "tech-a", "pm-b")]
        batch = build_change_notification_batch(previous, current, self.contacts, WEEK)
        managers = {
            draft.recipient_id for draft in batch.drafts if draft.audience == "project_manager"
        }
        self.assertEqual(managers, {"pm-a", "pm-b"})

    def test_no_change_produces_no_drafts(self) -> None:
        rows = [assignment("S-1")]
        batch = build_change_notification_batch(rows, list(rows), self.contacts, WEEK)
        self.assertEqual(batch.drafts, ())
        self.assertEqual(batch.missing_contact_ids, ())

    def test_weekly_body_contains_confirmation_and_outside_schedule(self) -> None:
        row = assignment("S-1", outside=True, confirmation="Tentative")
        batch = build_weekly_plan_batch([row], self.contacts, WEEK)
        technician = next(draft for draft in batch.drafts if draft.audience == "technician")
        self.assertIn("Tentative", technician.body)
        self.assertIn("hors horaire", technician.body)


if __name__ == "__main__":
    unittest.main()
