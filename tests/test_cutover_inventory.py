from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tools.cutover_inventory import (
    LEGACY_REQUIREMENTS,
    _scan_python_boundary,
    build_inventory,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


class CutoverInventoryTests(unittest.TestCase):
    def test_current_canonical_boundary_debt_is_explicit_and_has_no_regression(self) -> None:
        inventory = build_inventory(REPO_ROOT)

        self.assertEqual(inventory.unexpected_boundary_violations, ())
        self.assertGreaterEqual(len(inventory.known_boundary_debt), 1)
        self.assertEqual(
            {item.path for item in inventory.known_boundary_debt},
            {"app/application/runtime_services.py"},
        )
        self.assertTrue(
            all(
                item.imported_module.startswith("app.infrastructure.excel")
                for item in inventory.known_boundary_debt
            )
        )

    def test_current_inventory_keeps_runtime_and_migration_debt_visible(self) -> None:
        inventory = build_inventory(REPO_ROOT)

        self.assertIn("main.py", inventory.legacy_entrypoints)
        self.assertIn("Lancer_Application.bat", inventory.legacy_entrypoints)
        self.assertIn("Installer.bat", inventory.legacy_entrypoints)
        self.assertIn("tools/cutover_excel_to_sql.py", inventory.migration_tools)
        self.assertEqual(set(inventory.legacy_requirements), LEGACY_REQUIREMENTS)
        self.assertIn("app/v13.py", inventory.versioned_modules)
        self.assertIn("app/v18.py", inventory.versioned_modules)
        self.assertIn("app/v172_nicegui_compat.py", inventory.compatibility_modules)
        self.assertIn("app/ui.py", inventory.ui_modules)
        self.assertIn("app/excel_repository.py", inventory.excel_modules)

    def test_runtime_composition_is_counted_and_classified(self) -> None:
        inventory = build_inventory(REPO_ROOT)
        steps = dict(inventory.runtime_steps)

        self.assertGreater(len(steps), 20)
        self.assertEqual(steps.get("nicegui_compat"), "compatibility")
        self.assertEqual(steps.get("features"), "legacy")
        self.assertEqual(steps.get("operational_planning_page"), "application")
        self.assertEqual(steps.get("communication_ui"), "communications")

    def test_forbidden_external_dependency_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "app/server/bad.py"
            path.parent.mkdir(parents=True)
            path.write_text("import xlwings\n", encoding="utf-8")

            violations = _scan_python_boundary(
                root,
                path,
                allowed_prefixes=("app.server", "app.application"),
            )

        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].imported_module, "xlwings")

    def test_legacy_app_import_is_detected_but_canonical_import_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "app/server/bad.py"
            path.parent.mkdir(parents=True)
            path.write_text(
                "from app.application import ApplicationFacade\n"
                "from app.excel_repository import ExcelRepository\n",
                encoding="utf-8",
            )

            violations = _scan_python_boundary(
                root,
                path,
                allowed_prefixes=("app.server", "app.application"),
            )

        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].imported_module, "app.excel_repository")

    def test_relative_import_from_package_init_is_resolved_inside_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "app/application/__init__.py"
            path.parent.mkdir(parents=True)
            path.write_text("from .commands import DemandCreateCommand\n", encoding="utf-8")

            violations = _scan_python_boundary(
                root,
                path,
                allowed_prefixes=("app.application", "app.domain"),
            )

        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
