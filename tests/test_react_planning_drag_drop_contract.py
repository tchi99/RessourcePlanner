from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReactPlanningDragDropContractTests(unittest.TestCase):
    def test_drag_payloads_keep_shift_and_segment_intents_distinct(self) -> None:
        drag = (ROOT / "frontend" / "src" / "planningDragDrop.ts").read_text(encoding="utf-8")

        self.assertIn("application/x-resourceplanner-shift", drag)
        self.assertIn("application/x-resourceplanner-segment", drag)
        self.assertIn('kind: "SHIFT"', drag)
        self.assertIn('kind: "SEGMENT"', drag)
        self.assertIn("writeShiftDrag", drag)
        self.assertIn("writeSegmentDrag", drag)

    def test_shift_drop_uses_explicit_backend_move_contract_without_optimistic_snapshot_edit(self) -> None:
        page = (ROOT / "frontend" / "src" / "PlanningPage.tsx").read_text(encoding="utf-8")
        api = (ROOT / "frontend" / "src" / "api.ts").read_text(encoding="utf-8")

        self.assertIn("moveAllocation(payload.allocation_id", page)
        self.assertIn("planning-drop-day", page)
        self.assertIn("writeShiftDrag", page)
        self.assertIn("setRefreshKey", page)
        self.assertIn("/move", api)
        self.assertNotIn("setSnapshot((current)", page)

    def test_unassigned_segment_can_be_dragged_to_resource_but_buttons_remain_fallback(self) -> None:
        panel = (ROOT / "frontend" / "src" / "PlanningActionPanel.tsx").read_text(encoding="utf-8")
        page = (ROOT / "frontend" / "src" / "PlanningPage.tsx").read_text(encoding="utf-8")

        self.assertIn("writeSegmentDrag", panel)
        self.assertIn("Glisser vers une ressource", panel)
        self.assertIn("Trouver une ressource", panel)
        self.assertIn("Modifier le segment", panel)
        self.assertIn("assignSegment(payload.segment_id", page)
        self.assertIn("planning-drop-resource", page)
        self.assertIn("alternative clavier", page)

    def test_drag_drop_is_permission_gated_and_backend_rules_are_not_reimplemented(self) -> None:
        page = (ROOT / "frontend" / "src" / "PlanningPage.tsx").read_text(encoding="utf-8")

        self.assertIn('can("manage_planning")', page)
        self.assertIn("dragEnabled={canManagePlanning && !dropBusy}", page)
        self.assertNotIn("availability_hours_for_day", page)
        self.assertNotIn("manual_overallocation_impact", page)

    def test_backend_has_dedicated_move_route_and_audit_action(self) -> None:
        routes = (ROOT / "app" / "server" / "routes_commands.py").read_text(encoding="utf-8")
        audit = (ROOT / "app" / "infrastructure" / "sql" / "planning_audit.py").read_text(
            encoding="utf-8"
        )
        adapter = (ROOT / "app" / "infrastructure" / "sql" / "command_adapters.py").read_text(
            encoding="utf-8"
        )

        self.assertIn('/allocations/{allocation_id}/move', routes)
        self.assertIn("ManualAllocationMoveCommand", routes)
        self.assertIn('action="Déplacement quart"', audit)
        self.assertIn('shift.source = "MANUAL"', adapter)
        self.assertIn("shift.locked = True", adapter)


if __name__ == "__main__":
    unittest.main()
