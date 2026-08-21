from __future__ import annotations

from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import patch

from app.application.planning_service import PlanningService
from app.application.runtime_services import planning_service


class PlanningServiceTests(unittest.TestCase):
    def test_rebuild_delegates_once_and_returns_plain_dict(self) -> None:
        repository = object()
        calls: list[object] = []

        def rebuild(repo: object):
            calls.append(repo)
            return {"allocated_hours": 24.0, "engine": "pure"}

        result = PlanningService(repository, rebuild_planning=rebuild).rebuild()

        self.assertEqual(calls, [repository])
        self.assertEqual(result, {"allocated_hours": 24.0, "engine": "pure"})
        self.assertIsInstance(result, dict)

    def test_rebuild_propagates_domain_or_repository_failure(self) -> None:
        expected = RuntimeError("planning failed")

        def rebuild(_repo: object):
            raise expected

        with self.assertRaises(RuntimeError) as raised:
            PlanningService(object(), rebuild_planning=rebuild).rebuild()

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

    def test_application_service_has_no_ui_or_storage_dependency(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "application"
            / "planning_service.py"
        )
        source = path.read_text(encoding="utf-8")

        for forbidden in (
            "nicegui",
            "xlwings",
            "ExcelRepository",
            "v15_engine",
            "v14_engine",
            "v13",
        ):
            self.assertNotIn(forbidden, source)

    def test_runtime_adapter_does_not_import_legacy_engine_eagerly(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "application"
            / "runtime_services.py"
        )
        source = path.read_text(encoding="utf-8")

        self.assertNotIn("from .. import v15_engine", source)
        self.assertIn('import_module("app.v15_engine")', source)


if __name__ == "__main__":
    unittest.main()
