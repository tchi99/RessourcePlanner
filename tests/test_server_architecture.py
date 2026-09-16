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
        self.assertIn("SqlEmergencyDemandRepository", composition)
        self.assertIn("SqlSegmentRepositoryWithActiveDayMetrics", composition)
        self.assertIn("SqlPlanningCommandAdapter", composition)
        self.assertIn("SqlOverallocationAllocationCommandAdapter", composition)
        self.assertIn("OverallocationAuditedAllocationCommandAdapter", composition)
        self.assertIn("OverallocationAuditedSegmentRepository", composition)
        self.assertIn("SqlPeriodAwareApprovedDemandSyncAdapter", composition)
        self.assertIn("SqlPlannerQueryRepositoryWithLoadProfiles", composition)

        forbidden_sql_names = (
            "SqlEmergencyDemandRepository",
            "SqlSegmentRepositoryWithActiveDayMetrics",
            "SqlPlanningCommandAdapter",
            "SqlOverallocationAllocationCommandAdapter",
            "SqlPlannerQueryRepositoryWithLoadProfiles",
        )
        for filename in ("http.py", "routes_commands.py", "routes_reads.py"):
            source = (SERVER / filename).read_text(encoding="utf-8")
            for name in forbidden_sql_names:
                self.assertNotIn(name, source)

        # The HTTP composition boundary owns the request-scoped SQLAlchemy Session,
        # but route modules must remain transport/application-only.
        for filename in ("routes_commands.py", "routes_reads.py"):
            source = (SERVER / filename).read_text(encoding="utf-8")
            self.assertNotIn("sqlalchemy", source.casefold())

    def test_read_routes_depend_only_on_public_application_query_contract(self) -> None:
        source = (SERVER / "routes_reads.py").read_text(encoding="utf-8")
        self.assertIn("PlannerQueryPort", source)
        self.assertIn("ProjectReadModel", source)
        self.assertIn("ShiftReadModel", source)
        self.assertNotIn("infrastructure.sql", source)
        self.assertNotIn("ResourceRequirement", source)
        self.assertNotIn("WorkforceRequest", source)


if __name__ == "__main__":
    unittest.main()
