from __future__ import annotations

import ast
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import patch

from app.application.planning_service import PlanningService
from app.application.runtime_services import planning_service


class _PlanningCommands:
    def __init__(self, result=None, failure: Exception | None = None) -> None:
        self.calls = 0
        self.result = result or {"allocated_hours": 24.0, "engine": "pure"}
        self.failure = failure

    def rebuild(self):
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        return self.result


class PlanningServiceTests(unittest.TestCase):
    def test_rebuild_delegates_once_and_returns_plain_dict(self) -> None:
        commands = _PlanningCommands()

        result = PlanningService(commands).rebuild()

        self.assertEqual(commands.calls, 1)
        self.assertEqual(result, {"allocated_hours": 24.0, "engine": "pure"})
        self.assertIsInstance(result, dict)

    def test_rebuild_propagates_domain_or_repository_failure(self) -> None:
        expected = RuntimeError("planning failed")
        commands = _PlanningCommands(failure=expected)

        with self.assertRaises(RuntimeError) as raised:
            PlanningService(commands).rebuild()

        self.assertIs(raised.exception, expected)

    def test_runtime_adapter_resolves_selected_engine_at_execution_time(self) -> None:
        repository = object()
        service = planning_service(repository)
        calls: list[str] = []
        fake_engine = ModuleType("app.v15_engine")

        def selected_engine(repo: object):
            self.assertIs(repo, repository)
            calls.append("selected")
            return {"allocated_hours": 12.0, "engine": "selected"}

        fake_engine.rebuild_allocations = selected_engine  # type: ignore[attr-defined]
        with patch.dict(sys.modules, {"app.v15_engine": fake_engine}):
            result = service.rebuild()

        self.assertEqual(calls, ["selected"])
        self.assertEqual(result["engine"], "selected")

    def test_application_service_has_no_ui_storage_or_v1_import(self) -> None:
        path = Path(__file__).resolve().parents[1] / "app" / "application" / "planning_service.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported_modules: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported_modules.append(node.module or "")

        forbidden_prefixes = (
            "nicegui",
            "xlwings",
            "app.excel_repository",
            "app.v13",
            "app.v14",
            "app.v15",
            "app.v16",
            "app.v17",
            "app.v18",
        )
        for module in imported_modules:
            self.assertFalse(
                module.startswith(forbidden_prefixes),
                f"planning_service.py must stay transport/storage agnostic; found import {module}",
            )

    def test_runtime_services_contains_no_direct_v1_bridge(self) -> None:
        path = Path(__file__).resolve().parents[1] / "app" / "application" / "runtime_services.py"
        source = path.read_text(encoding="utf-8")

        for token in (
            "app.v15_engine",
            "app.v15_refinements",
            "_sync_segments_to_approved_demand",
            "rebuild_allocations",
        ):
            self.assertNotIn(token, source)
        self.assertIn("ExcelPlanningCommandAdapter", source)
        self.assertIn("ExcelApprovedDemandSyncAdapter", source)


if __name__ == "__main__":
    unittest.main()
