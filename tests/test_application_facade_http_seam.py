from __future__ import annotations

import ast
from datetime import date
from pathlib import Path
from types import SimpleNamespace
import unittest

from app.application import (
    ApplicationError,
    ApplicationFacade,
    DemandCreateCommand,
)


class _Demands:
    def create_command(self, _command):
        return "DMO-API-1"

    def modify_command(self, _command):
        raise AssertionError("not used")

    def submit_command(self, _command):
        raise AssertionError("not used")

    def approve_command(self, _command):
        raise AssertionError("not used")

    def request_correction_command(self, _command):
        raise AssertionError("not used")

    def cancel_command(self, _command):
        raise AssertionError("not used")


class _Unused:
    def __getattr__(self, name):
        raise AssertionError(f"unexpected use: {name}")


class _QuickUnused(_Unused):
    def create_command(self, _command):
        return SimpleNamespace(segment_id="", allocation_id="")


class _PlanningUnused(_Unused):
    def rebuild_command(self, _command):
        return {}


def facade_fixture() -> ApplicationFacade:
    return ApplicationFacade(
        demands=_Demands(),  # type: ignore[arg-type]
        segments=_Unused(),  # type: ignore[arg-type]
        allocations=_Unused(),  # type: ignore[arg-type]
        quick_shifts=_QuickUnused(),  # type: ignore[arg-type]
        planning=_PlanningUnused(),  # type: ignore[arg-type]
    )


def fictive_http_post_demand(facade: ApplicationFacade, payload: dict) -> tuple[int, dict]:
    """Framework-free adapter with the shape a future FastAPI route will use."""

    try:
        command = DemandCreateCommand.from_mapping(payload, submit=True)
        result = facade.create_demand(command)
        return 201, result.to_dict()
    except ApplicationError as exc:
        return 422, exc.as_dict()


class ApplicationFacadeHttpSeamTests(unittest.TestCase):
    def test_route_adapter_needs_only_public_application_surface(self) -> None:
        status, payload = fictive_http_post_demand(
            facade_fixture(),
            {
                "NumeroProjet": "P-API",
                "DateDebutSouhaitee": date(2026, 8, 26),
            },
        )

        self.assertEqual(status, 201)
        self.assertEqual(payload["demand_number"], "DMO-API-1")
        self.assertEqual(payload["status"], "Soumise")

    def test_route_adapter_translates_validation_without_transport_dependency(self) -> None:
        status, payload = fictive_http_post_demand(
            facade_fixture(),
            {"NumeroProjet": "", "DateDebutSouhaitee": date(2026, 8, 26)},
        )

        self.assertEqual(status, 422)
        self.assertEqual(payload["code"], "demand_project_required")

    def test_seam_imports_only_public_application_surface(self) -> None:
        source = Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        application_imports = [
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and (node.module or "").startswith("app.application")
        ]

        self.assertEqual(application_imports, ["app.application"])
        all_imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                all_imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                all_imports.append(node.module or "")
        forbidden_modules = (
            "fastapi",
            "pydantic",
            "nicegui",
            "xlwings",
            "app.excel_repository",
            "app.application.demand_service",
            "app.application.segment_service",
            "app.application.allocation_service",
            "app.application.quick_shift_service",
            "app.application.planning_service",
        )
        for module in all_imports:
            self.assertNotIn(module, forbidden_modules)


if __name__ == "__main__":
    unittest.main()
