from __future__ import annotations

import unittest

from app.application.allocation_service import AllocationService


class _Commands:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def create_manual(self, segment, technician, day, hours, overtime=False, note=""):
        self.calls.append(("create", segment, technician, day, hours, overtime, note))
        return "MAN-1"

    def update_manual(self, identifier, technician, day, hours, overtime=False, note=""):
        self.calls.append(("update", identifier, technician, day, hours, overtime, note))

    def release_manual(self, identifier):
        self.calls.append(("release", identifier))

    def delete_manual(self, identifier):
        self.calls.append(("delete", identifier))

    def assign_segment(self, segment, technician):
        self.calls.append(("assign", segment, technician))
        return {"allocated_hours": 7.5, "unallocated_hours": 0.0}


class AllocationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.commands = _Commands()
        self.service = AllocationService(self.commands)

    def test_create_manual_normalizes_identity_and_preserves_payload(self) -> None:
        identifier = self.service.create_manual(
            " SEG-1 ", " Alice ", "2026-08-24", 4, True, " chantier "
        )

        self.assertEqual(identifier, "MAN-1")
        self.assertEqual(
            self.commands.calls,
            [("create", "SEG-1", "Alice", "2026-08-24", 4, True, " chantier ")],
        )

    def test_update_manual_represents_move_and_reassignment_as_one_intent(self) -> None:
        self.service.update_manual("MAN-4", "Bob", "2026-08-25", 6.5, False, "déplacé")

        self.assertEqual(
            self.commands.calls,
            [("update", "MAN-4", "Bob", "2026-08-25", 6.5, False, "déplacé")],
        )

    def test_release_and_delete_route_through_command_port(self) -> None:
        self.service.release_manual("MAN-2")
        self.service.delete_manual("MAN-3")

        self.assertEqual(
            self.commands.calls,
            [("release", "MAN-2"), ("delete", "MAN-3")],
        )

    def test_assign_segment_returns_engine_summary(self) -> None:
        summary = self.service.assign_segment("SEG-9", "Caroline")

        self.assertEqual(summary["allocated_hours"], 7.5)
        self.assertEqual(self.commands.calls, [("assign", "SEG-9", "Caroline")])

    def test_empty_identifiers_are_rejected_before_command_adapter(self) -> None:
        with self.assertRaises(ValueError):
            self.service.create_manual("", "Alice", "2026-08-24", 4)
        with self.assertRaises(ValueError):
            self.service.update_manual("", "Alice", "2026-08-24", 4)
        with self.assertRaises(ValueError):
            self.service.assign_segment("SEG-1", "")

        self.assertEqual(self.commands.calls, [])


if __name__ == "__main__":
    unittest.main()
