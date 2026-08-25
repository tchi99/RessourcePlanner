from __future__ import annotations

from datetime import date
import unittest

from app.application.allocation_service import AllocationService
from app.application.commands import ManualAllocationCreateCommand
from app.application.errors import ApplicationValidationError


class _Commands:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.failure: Exception | None = None

    def create_manual(self, segment, technician, day, hours, overtime=False, note=""):
        self.calls.append(("create", segment, technician, day, hours, overtime, note))
        if self.failure is not None:
            raise self.failure
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

    def test_legacy_create_normalizes_to_typed_command_before_port(self) -> None:
        identifier = self.service.create_manual(
            " SEG-1 ", " Alice ", "2026-08-24", 4, True, " chantier "
        )

        self.assertEqual(identifier, "MAN-1")
        self.assertEqual(
            self.commands.calls,
            [
                (
                    "create",
                    "SEG-1",
                    "Alice",
                    date(2026, 8, 24),
                    4.0,
                    True,
                    " chantier ",
                )
            ],
        )

    def test_typed_create_command_is_canonical_entry_point(self) -> None:
        identifier = self.service.create_manual_command(
            ManualAllocationCreateCommand(
                segment_id="SEG-2",
                technician="Bob",
                day=date(2026, 8, 25),
                hours=6.5,
                note="déplacement",
            )
        )

        self.assertEqual(identifier, "MAN-1")
        self.assertEqual(
            self.commands.calls,
            [("create", "SEG-2", "Bob", date(2026, 8, 25), 6.5, False, "déplacement")],
        )

    def test_update_release_delete_and_assign_route_through_command_port(self) -> None:
        self.service.update_manual("MAN-4", "Bob", "2026-08-25", 6.5, False, "déplacé")
        self.service.release_manual("MAN-2")
        self.service.delete_manual("MAN-3")
        summary = self.service.assign_segment("SEG-9", "Caroline")

        self.assertEqual(summary["allocated_hours"], 7.5)
        self.assertEqual(
            self.commands.calls,
            [
                ("update", "MAN-4", "Bob", date(2026, 8, 25), 6.5, False, "déplacé"),
                ("release", "MAN-2"),
                ("delete", "MAN-3"),
                ("assign", "SEG-9", "Caroline"),
            ],
        )

    def test_validation_errors_are_structured_before_adapter(self) -> None:
        with self.assertRaises(ApplicationValidationError) as raised:
            self.service.create_manual("", "Alice", "2026-08-24", 4)
        self.assertEqual(raised.exception.code, "allocation_segment_required")

        with self.assertRaises(ApplicationValidationError):
            self.service.update_manual("", "Alice", "2026-08-24", 4)
        with self.assertRaises(ApplicationValidationError):
            self.service.assign_segment("SEG-1", "")

        self.assertEqual(self.commands.calls, [])

    def test_adapter_value_error_is_translated_for_http_boundary(self) -> None:
        self.commands.failure = ValueError("hors horaire requis")

        with self.assertRaises(ApplicationValidationError) as raised:
            self.service.create_manual_command(
                ManualAllocationCreateCommand(
                    segment_id="SEG-1",
                    technician="Alice",
                    day=date(2026, 8, 24),
                    hours=4,
                )
            )

        self.assertEqual(str(raised.exception), "hors horaire requis")
        self.assertEqual(raised.exception.code, "allocation_create_invalid")
        self.assertEqual(raised.exception.context["segment_id"], "SEG-1")


if __name__ == "__main__":
    unittest.main()
