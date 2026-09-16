from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "frontend" / "src" / "PlanningHistoryPanel.tsx"
API = ROOT / "frontend" / "src" / "planningHistoryApi.ts"
SHIFT_EDITOR = ROOT / "frontend" / "src" / "ShiftEditor.tsx"
SEGMENT_EDITOR = ROOT / "frontend" / "src" / "SegmentEditor.tsx"
MAIN = ROOT / "frontend" / "src" / "main.tsx"


class FrontendPlanningHistoryContractTests(unittest.TestCase):
    def test_planning_editors_expose_real_audit_panel(self) -> None:
        shift_editor = SHIFT_EDITOR.read_text(encoding="utf-8")
        segment_editor = SEGMENT_EDITOR.read_text(encoding="utf-8")
        self.assertIn('entityType="SHIFT"', shift_editor)
        self.assertIn('reference={shift.allocation_id}', shift_editor)
        self.assertIn('entityType="SEGMENT"', segment_editor)
        self.assertIn('reference={segmentId}', segment_editor)

    def test_frontend_reads_backend_history_routes_only(self) -> None:
        api = API.read_text(encoding="utf-8")
        self.assertIn("/api/v1/segments/", api)
        self.assertIn("/api/v1/shifts/", api)
        self.assertIn("/history", api)
        self.assertNotIn("localStorage", api)

    def test_panel_displays_actor_timestamp_and_structured_changes(self) -> None:
        panel = PANEL.read_text(encoding="utf-8")
        self.assertIn("Historique des changements", panel)
        self.assertIn("actor_name", panel)
        self.assertIn("occurred_at", panel)
        self.assertIn("parsed.changes", panel)

    def test_planning_history_styles_are_loaded(self) -> None:
        main = MAIN.read_text(encoding="utf-8")
        self.assertIn('import "./planning-history.css"', main)


if __name__ == "__main__":
    unittest.main()
