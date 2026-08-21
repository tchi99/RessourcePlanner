from __future__ import annotations

import unittest

from app.application.allocation_service import AllocationService


class AllocationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = object()
        self.calls: list[tuple] = []

        def create(repo, segment, technician, day, hours, overtime, note):
            self.calls.append(("create", repo, segment, technician, day, hours, overtime, note))
            return "MAN-1"

        def update(repo, identifier, technician, day, hours, overtime, note):
            self.calls.append(("update", repo, identifier, technician, day, hours, overtime, note))

        def release(repo, identifier):
            self.calls.append(("release", repo, identifier))

        def delete(repo, identifier):
            self.calls.append(("delete", repo, identifier))

        def assign(repo, segment, technician):
            self.calls.append(("assign", repo, segment, technician))
            return {"allocated_hours": 7.5, "unallocated_hours": 0.0}

        self.service = AllocationService(
            self.repository,
            create_manual_record=create,
            update_manual_record=update,
            release_manual_record=release,
            delete_manual_record=delete,
            assign_segment_record=assign,
        )

    def test_create_manual_normalizes_identity_and_preserves_payload(self) -> None:
        identifier = self.service.create_manual(
            " SEG-1 ", " Alice ", "2026-08-24", 4, True, " chantier "
        )

        self.assertEqual(identifier, "MAN-1")
        self.assertEqual(
            self.calls,
            [
                (
                    "create",
                    self.repository,
                    "SEG-1",
                    "Alice",
                    "2026-08-24",
                    4,
                    True,
                    " chantier ",
                )
            ],
        )

    def test_update_manual_represents_move_and_reassignment_as_one_intent(self) -> None:
        self.service.update_manual("MAN-4", "Bob", "2026-08-25", 6.5, False, "déplacé")

        self.assertEqual(
            self.calls,
            [
                (
                    "update",
                    self.repository,
                    "MAN-4",
                    "Bob",
                    "2026-08-25",
                    6.5,
                    False,
                    "déplacé",
                )
            ],
        )

    def test_release_and_delete_route_through_adapters(self) -> None:
        self.service.release_manual("MAN-2")
        self.service.delete_manual("MAN-3")

        self.assertEqual(
            self.calls,
            [
                ("release", self.repository, "MAN-2"),
                ("delete", self.repository, "MAN-3"),
            ],
        )

    def test_assign_segment_returns_engine_summary(self) -> None:
        summary = self.service.assign_segment("SEG-9", "Caroline")

        self.assertEqual(summary["allocated_hours"], 7.5)
        self.assertEqual(
            self.calls,
            [("assign", self.repository, "SEG-9", "Caroline")],
        )

    def test_empty_identifiers_are_rejected_before_storage_adapter(self) -> None:
        with self.assertRaises(ValueError):
            self.service.create_manual("", "Alice", "2026-08-24", 4)
        with self.assertRaises(ValueError):
            self.service.update_manual("", "Alice", "2026-08-24", 4)
        with self.assertRaises(ValueError):
            self.service.assign_segment("SEG-1", "")

        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
