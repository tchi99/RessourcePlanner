from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "app" / "server"


class ServerArchitectureTests(unittest.TestCase):
    def test_server_package_has_no_excel_nicegui_or_versioned_runtime_imports(self) -> None:
        forbidden = (
            "nicegui",
            "xlwings",
            "excel_repository",
            "app.v13",
            "app.v14",
            "app.v15",
            "app.v16",
            "app.v17",
            "app.v18",
        )
        for path in SERVER.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            imports: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.append(node.module or "")
            for name in forbidden:
                self.assertFalse(
                    any(name in module for module in imports),
                    f"{path.name} leaks forbidden dependency: {name}",
                )

    def test_http_boundary_does_not_run_alembic_or_import_business_services(self) -> None:
        source = (SERVER / "http.py").read_text(encoding="utf-8")
        self.assertNotIn("alembic", source.casefold())
        self.assertNotIn("DemandService", source)
        self.assertNotIn("SegmentService", source)
        self.assertNotIn("QuickShiftService", source)
        self.assertNotIn("SqlDemandRepository", source)
        self.assertIn("ApplicationFacade", source)

    def test_composition_root_is_the_only_server_file_wiring_sql_adapters(self) -> None:
        composition = (SERVER / "composition.py").read_text(encoding="utf-8")
        self.assertIn("SqlDemandRepository", composition)
        self.assertIn("SqlSegmentRepository", composition)
        self.assertIn("SqlPlanningCommandAdapter", composition)
        self.assertIn("SqlAllocationCommandAdapter", composition)
        self.assertIn("SqlApprovedDemandSyncAdapter", composition)

        http = (SERVER / "http.py").read_text(encoding="utf-8")
        self.assertNotIn("SqlDemandRepository", http)
        self.assertNotIn("SqlSegmentRepository", http)
        self.assertNotIn("SqlPlanningCommandAdapter", http)


if __name__ == "__main__":
    unittest.main()
