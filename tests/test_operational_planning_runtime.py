from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

from app.operational_planning_runtime import install_allocation_total_guard


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


class _CellContext:
    def __init__(self) -> None:
        self.calls: list[tuple[object, str, object, str | None]] = []

    def validate_locked_total(
        self,
        repo: object,
        segment_id: str,
        hours: object,
        *,
        exclude_allocation: str | None = None,
    ) -> None:
        self.calls.append((repo, segment_id, hours, exclude_allocation))


class OperationalPlanningRuntimeTests(unittest.TestCase):
    def test_allocation_guard_preserves_create_and_update_behavior(self) -> None:
        calls: list[tuple[str, tuple[object, ...]]] = []
        repository = object()

        def create(*args: object) -> str:
            calls.append(("create", args))
            return "A-NEW"

        def update(*args: object) -> None:
            calls.append(("update", args))

        engine = SimpleNamespace(
            create_manual_allocation=create,
            update_manual_allocation=update,
            allocation_by_id=lambda _repo, identifier: {
                "IDAllocation": identifier,
                "IDSegment": "SEG-2",
            },
        )
        context = _CellContext()

        install_allocation_total_guard(engine, context)
        created = engine.create_manual_allocation(
            repository, "SEG-1", "Alice", "2026-08-25", 4, False, "note"
        )
        engine.update_manual_allocation(
            repository, "A-1", "Bob", "2026-08-26", 3, True, "move"
        )

        self.assertEqual(created, "A-NEW")
        self.assertEqual(
            context.calls,
            [(repository, "SEG-1", 4, None), (repository, "SEG-2", 3, "A-1")],
        )
        self.assertEqual([name for name, _args in calls], ["create", "update"])

    def test_runtime_module_is_non_versioned(self) -> None:
        source = (APP / "operational_planning_runtime.py").read_text(encoding="utf-8")
        self.assertIn("install_allocation_total_guard", source)
        self.assertIn("install_operational_planning_style", source)
        self.assertIn(".v17-draggable", source)
        for version in ("v13", "v14", "v15", "v16", "v17", "v18"):
            self.assertNotIn(f"from . import {version}", source)
            self.assertNotIn(f"from .{version}", source)

    def test_runtime_performance_targets_extracted_split_handler(self) -> None:
        source = (APP / "runtime_performance_compat.py").read_text(encoding="utf-8")
        self.assertIn("drop_handler_module._split_allocation", source)
        self.assertIn("sorting_compat.move_manual_resource", source)
        self.assertNotIn("v171_performance", source)
        self.assertNotIn("v17._split_allocation", source)

    def test_no_application_module_imports_retired_v17_module(self) -> None:
        self.assertFalse((APP / "v17.py").exists())
        offenders: list[str] = []
        for path in APP.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom) or node.level != 1:
                    continue
                if node.module == "v17":
                    offenders.append(path.name)
                    continue
                if node.module is None and any(alias.name == "v17" for alias in node.names):
                    offenders.append(path.name)
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
