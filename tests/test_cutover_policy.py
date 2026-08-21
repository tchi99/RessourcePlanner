from __future__ import annotations

import ast
import unittest
from pathlib import Path

from app.domain.cutover_policy import (
    GUARDED_PURE_MODE,
    LEGACY_MODE,
    PURE_MODE,
    evaluate_cutover_gate,
    normalize_planning_engine_mode,
)


class CutoverPolicyTests(unittest.TestCase):
    def test_default_mode_is_pure(self) -> None:
        self.assertEqual(normalize_planning_engine_mode(None), PURE_MODE)
        self.assertEqual(normalize_planning_engine_mode(""), PURE_MODE)

    def test_pure_mode_is_accepted_case_insensitively(self) -> None:
        self.assertEqual(normalize_planning_engine_mode("PURE"), PURE_MODE)

    def test_guarded_mode_is_accepted_case_insensitively(self) -> None:
        self.assertEqual(normalize_planning_engine_mode("GUARDED_PURE"), GUARDED_PURE_MODE)

    def test_unknown_explicit_mode_falls_back_to_legacy(self) -> None:
        self.assertEqual(normalize_planning_engine_mode("typo"), LEGACY_MODE)

    def test_exact_shadow_match_allows_pure_engine(self) -> None:
        decision = evaluate_cutover_gate(shadow_matches=True, unsupported_segment_count=0)
        self.assertTrue(decision.use_pure_engine)
        self.assertEqual(decision.reason, "shadow_match")

    def test_shadow_mismatch_keeps_legacy(self) -> None:
        decision = evaluate_cutover_gate(shadow_matches=False, unsupported_segment_count=0)
        self.assertFalse(decision.use_pure_engine)
        self.assertEqual(decision.reason, "shadow_mismatch")

    def test_unsupported_segments_keep_legacy_even_when_comparable_part_matches(self) -> None:
        decision = evaluate_cutover_gate(shadow_matches=True, unsupported_segment_count=1)
        self.assertFalse(decision.use_pure_engine)
        self.assertEqual(decision.reason, "unsupported_segments")

    def test_direct_pure_function_has_no_legacy_rebuild_dependency(self) -> None:
        """Keep the lightweight CI invariant without importing NiceGUI/xlwings modules."""
        source = Path("app/planning_cutover.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        function = next(
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "rebuild_allocations_pure"
        )
        referenced_names = {
            node.id
            for node in ast.walk(function)
            if isinstance(node, ast.Name)
        }
        called_attributes = {
            node.func.attr
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        called_names = {
            node.func.id
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }

        self.assertNotIn("legacy_rebuild", referenced_names)
        self.assertNotIn("rebuild_allocations_guarded", referenced_names)
        self.assertIn("build_planning_snapshot", called_names)
        self.assertIn("build_shadow_report_from_snapshot", called_names)
        self.assertNotIn("build_shadow_report", called_names)
        self.assertIn("_write_allocations", called_attributes)


if __name__ == "__main__":
    unittest.main()
