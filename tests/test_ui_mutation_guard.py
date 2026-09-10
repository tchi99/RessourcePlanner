from __future__ import annotations

from pathlib import Path
import unittest

from app.ui_mutation_guard import MutationGate, set_actions_enabled


class FakeAction:
    def __init__(self) -> None:
        self.enabled = True
        self.changes: list[bool] = []

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self.changes.append(enabled)


class MutationGateTests(unittest.TestCase):
    def test_begin_is_one_shot_and_disables_visible_actions(self) -> None:
        first = FakeAction()
        second = FakeAction()
        gate = MutationGate()

        self.assertTrue(gate.begin([first, second]))
        self.assertTrue(gate.running)
        self.assertFalse(first.enabled)
        self.assertFalse(second.enabled)
        self.assertFalse(gate.begin([first, second]))
        self.assertEqual(first.changes, [False])

    def test_success_seals_dialog_gate_until_explicit_reset(self) -> None:
        action = FakeAction()
        gate = MutationGate()

        self.assertTrue(gate.begin([action]))
        gate.succeed()
        self.assertTrue(gate.completed)
        self.assertFalse(gate.begin([action]))
        self.assertFalse(action.enabled)

        gate.reset([action])
        self.assertTrue(action.enabled)
        self.assertTrue(gate.begin([action]))

    def test_retry_reopens_failed_attempt_and_reenables_action(self) -> None:
        action = FakeAction()
        gate = MutationGate()

        self.assertTrue(gate.begin([action]))
        gate.retry([action])
        self.assertTrue(action.enabled)
        self.assertFalse(gate.running)
        self.assertTrue(gate.begin([action]))

    def test_action_helper_ignores_missing_controls(self) -> None:
        action = FakeAction()
        set_actions_enabled([None, object(), action], False)
        self.assertFalse(action.enabled)


class MutationGuardArchitectureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app_dir = Path(__file__).resolve().parents[1] / "app"

    def source(self, filename: str) -> str:
        return (self.app_dir / filename).read_text(encoding="utf-8")

    def test_guard_policy_has_no_ui_or_storage_import_dependency(self) -> None:
        source = self.source("ui_mutation_guard.py").lower()
        for forbidden_import in (
            "from nicegui",
            "import nicegui",
            "from sqlalchemy",
            "import sqlalchemy",
            "from .excel_repository",
            "import xlwings",
        ):
            self.assertNotIn(forbidden_import, source)

    def test_demand_create_edit_uses_shared_dialog_gate_and_disables_actions(self) -> None:
        source = self.source("demand_editor_ui.py")
        self.assertIn("mutation_gate = MutationGate()", source)
        self.assertGreaterEqual(source.count("mutation_gate.begin(mutation_actions)"), 3)
        self.assertIn("mutation_gate.retry(mutation_actions)", source)

    def test_approval_dialog_is_guarded(self) -> None:
        source = self.source("demand_requests_page.py")
        approval = source[source.index("def _open_approval_dialog"):]
        self.assertIn("mutation_gate.begin(mutation_actions)", approval)
        self.assertIn("mutation_gate.succeed()", approval)

    def test_segment_create_update_and_cancel_share_one_gate(self) -> None:
        source = self.source("segment_editor_ui.py")
        self.assertIn("mutation_gate = MutationGate()", source)
        self.assertGreaterEqual(source.count("mutation_gate.begin(mutation_actions)"), 2)
        self.assertGreaterEqual(source.count("mutation_gate.succeed()"), 2)

    def test_quick_shift_and_existing_segment_manual_shift_are_guarded(self) -> None:
        source = self.source("quick_shift_ui.py")
        self.assertIn("mutation_gate.begin(mutation_actions)", source)
        self.assertEqual(source.count("_quick_shift_service(owner.repo).create("), 1)
        self.assertEqual(source.count("_allocation_service(owner.repo).create_manual("), 1)
        self.assertGreaterEqual(source.count("mutation_gate.succeed()"), 2)

    def test_recalculation_uses_reusable_cooldown_gate_and_visible_button(self) -> None:
        service_source = self.source("planning_service_ui.py")
        header_source = self.source("operational_planning_header_filters.py")
        self.assertIn("_planning_recalculate_gate", service_source)
        self.assertIn("RECALCULATE_REOPEN_SECONDS", service_source)
        self.assertIn("gate.begin(actions)", service_source)
        self.assertIn("lambda: gate.reset(actions)", service_source)
        self.assertIn("_planning_recalculate_action", header_source)


if __name__ == "__main__":
    unittest.main()
