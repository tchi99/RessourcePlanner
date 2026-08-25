from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
APPLICATION = APP / "application"


class CommandPortArchitectureTests(unittest.TestCase):
    def test_core_application_services_do_not_import_ui_excel_or_v1_modules(self) -> None:
        service_files = (
            "allocation_service.py",
            "planning_service.py",
            "quick_shift_service.py",
            "demand_service.py",
            "segment_service.py",
        )
        forbidden = (
            "nicegui",
            "xlwings",
            "excel_repository",
            ".v13",
            ".v14",
            ".v15",
            ".v16",
            ".v17",
            ".v18",
            "app.v13",
            "app.v14",
            "app.v15",
            "app.v16",
            "app.v17",
            "app.v18",
        )

        for filename in service_files:
            source = (APPLICATION / filename).read_text(encoding="utf-8")
            tree = ast.parse(source)
            imports: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.append(node.module or "")
            for module in imports:
                self.assertFalse(
                    any(token in module for token in forbidden),
                    f"{filename} leaks transport/storage/V1 dependency: {module}",
                )

    def test_runtime_services_has_no_direct_versioned_bridge_or_callback_composition(self) -> None:
        source = (APPLICATION / "runtime_services.py").read_text(encoding="utf-8")
        for token in (
            "app.v13",
            "app.v14",
            "app.v15",
            "app.v16",
            "app.v17",
            "app.v18",
            "v15_engine",
            "v15_refinements",
            "_sync_segments_to_approved_demand",
            "rebuild_planning=lambda",
            "sync_approved_demand=lambda",
            "from_repository_port",
        ):
            self.assertNotIn(token, source)
        self.assertIn("DemandService(", source)
        self.assertIn("SegmentService(", source)
        self.assertIn("ExcelPlanningCommandAdapter", source)
        self.assertIn("ExcelApprovedDemandSyncAdapter", source)

    def test_demand_and_segment_services_store_ports_not_repository_context(self) -> None:
        demand = (APPLICATION / "demand_service.py").read_text(encoding="utf-8")
        segment = (APPLICATION / "segment_service.py").read_text(encoding="utf-8")

        for source in (demand, segment):
            self.assertNotIn("repository_context", source)
            self.assertNotIn("self._repository", source)
            self.assertNotIn("rebuild_planning", source)
        self.assertIn("ApprovedDemandSyncPort", demand)
        self.assertIn("PlanningCommandPort", demand)
        self.assertIn("SegmentRepositoryPort", segment)
        self.assertIn("PlanningCommandPort", segment)

    def test_quick_shift_ui_no_longer_calls_v15_engine_directly(self) -> None:
        source = (APP / "quick_shift_ui.py").read_text(encoding="utf-8")
        self.assertNotIn("v15_engine", source)
        self.assertIn("excel_allocation_commands", source)
        self.assertIn("ExcelSegmentRepository", source)

    def test_v1_dependencies_are_confined_to_excel_command_adapter(self) -> None:
        source = (
            APP / "infrastructure" / "excel" / "command_adapters.py"
        ).read_text(encoding="utf-8")
        self.assertIn('import_module("app.v15_engine")', source)
        self.assertIn('import_module("app.v15_refinements")', source)
        self.assertIn('import_module("app.v13")', source)


if __name__ == "__main__":
    unittest.main()
