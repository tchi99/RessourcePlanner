from __future__ import annotations

from pathlib import Path
import unittest

from app.application.planning_service import PlanningService
from app.application.runtime_services import planning_service
from app import v15_engine


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
        original = v15_engine.rebuild_allocations
        service = planning_service(repository)
        calls: list[str] = []

        def selected_engine(repo: object):
            self.assertIs(repo, repository)
            calls.append("selected")
            return {"allocated_hours": 12.0, "engine": "selected"}

        try:
            v15_engine.rebuild_allocations = selected_engine
            result = service.rebuild()
        finally:
            v15_engine.rebuild_allocations = original

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


if __name__ == "__main__":
    unittest.main()
