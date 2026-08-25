from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace
import unittest

from app.operational_planning_drop_handler import (
    DropHandlerBindings,
    handle_operational_planning_drop,
)


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


def _bindings(**overrides):
    values = {
        "parse_date": lambda value: value if isinstance(value, date) else None,
        "segment_by_id": lambda repo, segment_id: {
            "IDSegment": segment_id,
            "HeuresPrevues": 8.0,
        },
        "segment_dates": lambda segment: (None, None),
        "availability_hours": lambda repo, technician, day: 8.0,
        "availability_for_day": lambda repo, technician, day: {"available": True},
        "number": lambda value: float(value or 0),
        "truthy": lambda value: str(value or "").lower() in {"oui", "true", "1"},
        "update_manual_allocation": lambda *args, **kwargs: None,
        "delete_manual_allocation": lambda *args, **kwargs: None,
        "update_segment": lambda *args, **kwargs: None,
        "add_segment": lambda repo, values: "SEG-NEW",
        "create_manual_allocation": lambda *args, **kwargs: "ALLOC-NEW",
        "segment_overtime_field": "HorsHoraireAutorise",
        "rebuild_allocations": lambda repo: {"unallocated_hours": 0},
        "allocation_by_id": lambda repo, identifier: None,
        "is_missing_allocation": lambda allocation: False,
        "skill_message": lambda repo, technician, segment: ("OK", True),
    }
    values.update(overrides)
    return DropHandlerBindings(**values)


class FakeOwner:
    def __init__(self) -> None:
        self.repo = object()
        self.messages: list[str] = []

    def _after_write(self, message: str) -> None:
        self.messages.append(message)


class OperationalPlanningDropHandlerTests(unittest.TestCase):
    def test_segment_payload_assigns_backlog_segment(self) -> None:
        updates: list[tuple[str, dict[str, str]]] = []
        rebuilds: list[object] = []
        owner = FakeOwner()
        bindings = _bindings(
            parse_date=lambda value: date(2026, 8, 25),
            update_segment=lambda repo, segment_id, values: updates.append(
                (segment_id, values)
            ),
            rebuild_allocations=lambda repo: rebuilds.append(repo)
            or {"unallocated_hours": 0},
        )
        event = SimpleNamespace(
            args={
                "payload": "segment:SEG-2026-0042",
                "technician": "Mathieu",
                "date": "2026-08-25",
            }
        )

        handle_operational_planning_drop(owner, event, bindings=bindings)

        self.assertEqual(
            updates,
            [("SEG-2026-0042", {"Technicien": "Mathieu", "Statut": "Planifié"})],
        )
        self.assertEqual(rebuilds, [owner.repo])
        self.assertEqual(owner.messages, ["SEG-2026-0042 assigné à Mathieu"])

    def test_allocation_dropped_on_resource_reassigns_parent_segment(self) -> None:
        updates: list[tuple[str, dict[str, str]]] = []
        owner = FakeOwner()
        bindings = _bindings(
            parse_date=lambda value: None,
            allocation_by_id=lambda repo, identifier: {
                "IDAllocation": identifier,
                "IDSegment": "SEG-42",
                "Technicien": "Alex",
            },
            update_segment=lambda repo, segment_id, values: updates.append(
                (segment_id, values)
            ),
        )
        event = SimpleNamespace(
            args={
                "payload": "allocation:ALLOC-42",
                "technician": "Mathieu",
                "date": "",
            }
        )

        handle_operational_planning_drop(owner, event, bindings=bindings)

        self.assertEqual(
            updates,
            [("SEG-42", {"Technicien": "Mathieu", "Statut": "Planifié"})],
        )
        self.assertEqual(owner.messages, ["Segment réaffecté à Mathieu"])

    def test_unknown_payload_is_ignored(self) -> None:
        owner = FakeOwner()
        event = SimpleNamespace(
            args={"payload": "unknown:42", "technician": "Mathieu", "date": ""}
        )

        handle_operational_planning_drop(owner, event, bindings=_bindings())

        self.assertEqual(owner.messages, [])

    def test_extracted_handler_has_no_direct_versioned_imports(self) -> None:
        source = (APP / "operational_planning_drop_handler.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("class DropHandlerBindings", source)
        self.assertIn("def handle_operational_planning_drop(", source)
        self.assertIn("def register_operational_planning_drop_handler(", source)
        for versioned in ("v13", "v14", "v15", "v16", "v17"):
            self.assertNotIn(f"from . import {versioned}", source)
            self.assertNotIn(f"from .{versioned}", source)

    def test_v17_no_longer_owns_drop_workflow(self) -> None:
        source = (APP / "v17.py").read_text(encoding="utf-8")
        for retired in (
            "def _move_allocation_same_resource(",
            "def _open_move_confirmation(",
            "def _split_allocation(",
            "def _open_cross_resource_dialog(",
            "def _assign_backlog_segment(",
            "def _handle_drop(",
            "def _register_drop_handler(",
        ):
            self.assertNotIn(retired, source)
        self.assertIn("operational_planning_drop_handler_bindings()", source)
        self.assertIn("register_operational_planning_drop_handler(", source)


if __name__ == "__main__":
    unittest.main()
