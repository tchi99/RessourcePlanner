from __future__ import annotations

from datetime import date
from pathlib import Path
import unittest

from app.operational_planning_drag_drop import DROP_EVENT, make_draggable, make_drop_zone


class FakeElement:
    def __init__(self) -> None:
        self.props_values: list[str] = []
        self.class_values: list[str] = []
        self.events: dict[str, str] = {}

    def props(self, value: str) -> "FakeElement":
        self.props_values.append(value)
        return self

    def classes(self, value: str) -> "FakeElement":
        self.class_values.append(value)
        return self

    def on(self, event: str, *, js_handler: str) -> "FakeElement":
        self.events[event] = js_handler
        return self


class OperationalPlanningDragDropTests(unittest.TestCase):
    def test_make_draggable_preserves_payload_and_css_contract(self) -> None:
        element = FakeElement()

        result = make_draggable(element, "allocation:ALLOC-42")

        self.assertIs(result, element)
        self.assertIn("draggable=true", element.props_values)
        self.assertIn("v17-draggable", element.class_values)
        self.assertIn("allocation:ALLOC-42", element.events["dragstart"])
        self.assertIn("v17-dragging", element.events["dragstart"])
        self.assertIn("v17-dragging", element.events["dragend"])

    def test_make_drop_zone_emits_shared_event_with_resource_and_date(self) -> None:
        element = FakeElement()

        result = make_drop_zone(element, "Mathieu", date(2026, 8, 25))

        self.assertIs(result, element)
        self.assertEqual(DROP_EVENT, "v17-planning-drop")
        self.assertIn("v17-drop-zone", element.class_values)
        self.assertIn(DROP_EVENT, element.events["drop"])
        self.assertIn("Mathieu", element.events["drop"])
        self.assertIn("2026-08-25", element.events["drop"])
        self.assertIn("v17-drop-hover", element.events["dragover"])
        self.assertIn("v17-drop-hover", element.events["dragleave"])

    def test_drag_drop_module_has_no_versioned_imports(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "operational_planning_drag_drop.py"
        ).read_text(encoding="utf-8")

        for versioned in ("v13", "v14", "v15", "v16", "v17"):
            self.assertNotIn(f"from . import {versioned}", source)
            self.assertNotIn(f"from .{versioned}", source)


if __name__ == "__main__":
    unittest.main()
