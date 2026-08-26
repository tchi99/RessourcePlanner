from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "app" / "infrastructure" / "migration"
TOOL = ROOT / "tools" / "cutover_excel_to_sql.py"


class CutoverArchitectureTests(unittest.TestCase):
    def test_frozen_workbook_reader_has_no_excel_runtime_or_write_path(self) -> None:
        source = (MIGRATION / "openpyxl_reader.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")

        self.assertFalse(any("xlwings" in module for module in imports))
        self.assertNotIn("ExcelRepository", source)
        self.assertNotIn("save_workbook", source)
        self.assertNotIn(".save(", source)
        self.assertIn("read_only=True", source)
        self.assertIn("data_only=True", source)

    def test_cli_does_not_use_excel_repository_or_run_planning(self) -> None:
        source = TOOL.read_text(encoding="utf-8")
        self.assertNotIn("ExcelRepository", source)
        self.assertNotIn("xlwings", source)
        self.assertNotIn("rebuild", source.casefold())
        self.assertIn("command.upgrade", source)
        self.assertIn("transactional_session", source)
        self.assertIn("RESOURCEPLANNER_DATABASE_URL", source)

    def test_report_and_local_databases_are_gitignored(self) -> None:
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("cutover_report.json", ignored)
        self.assertIn("cutover_reports/", ignored)
        self.assertIn("*.db", ignored)
        self.assertIn("*.xlsx", ignored)
        self.assertIn("*.xlsm", ignored)


if __name__ == "__main__":
    unittest.main()
