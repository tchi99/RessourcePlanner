from __future__ import annotations

import ast
import unittest
from pathlib import Path

from app.domain.cutover_policy import PURE_MODE, normalize_planning_engine_mode


class CutoverPolicyTests(unittest.TestCase):
    @staticmethod
    def _planning_function(name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
        source = Path("app/planning_cutover.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        return next(
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
        )

    def test_old_or_unknown_modes_are_inert_and_normalize_to_pure(self) -> None:
        for value in (None, "", "PURE", "legacy", "guarded_pure", "typo"):
            self.assertEqual(normalize_planning_engine_mode(value), PURE_MODE)

    def test_runtime_contains_no_guarded_or_legacy_rebuild_path(self) -> None:
        source = Path("app/planning_cutover.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        function_names = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

        self.assertNotIn("rebuild_allocations_guarded", function_names)
        self.assertNotIn("legacy_rebuild", source)
        self.assertNotIn("guarded_pure", source)

    def test_direct_pure_function_has_one_snapshot_and_no_legacy_dependency(self) -> None:
        function = self._planning_function("rebuild_allocations_pure")
        referenced_names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
        called_attributes = {
            node.func.attr
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        called_names = [
            node.func.id
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]

        self.assertNotIn("legacy_rebuild", referenced_names)
        self.assertEqual(called_names.count("build_planning_snapshot"), 1)
        self.assertEqual(called_names.count("build_shadow_report_from_snapshot"), 1)
        self.assertIn("_write_allocations", called_attributes)

    def test_persistence_adapter_does_not_read_repository_again(self) -> None:
        function = self._planning_function("_pure_persistence_rows")
        argument_names = {argument.arg for argument in function.args.args}
        called_attributes = {
            node.func.attr
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }

        self.assertEqual(argument_names, {"snapshot", "report"})
        self.assertNotIn("_sheet_as_records", called_attributes)
        self.assertNotIn("allocation_records", called_attributes)


if __name__ == "__main__":
    unittest.main()
