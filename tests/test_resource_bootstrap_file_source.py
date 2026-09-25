from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from openpyxl import Workbook

from app.application.errors import ApplicationOperationError
from app.infrastructure.erp_export import ResourceBootstrapFileSource


HEADERS = [
    "external_id", "name", "email", "active", "resource_class",
    "sort_order", "working_days", "start_time", "end_time",
]


class ResourceBootstrapFileSourceTests(unittest.TestCase):
    def test_csv_reads_schedule_and_allows_missing_schedule(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "resources.csv"
            path.write_text(
                "external_id;name;email;active;resource_class;sort_order;working_days;start_time;end_time\n"
                "EMP-TEST-101;Technicien Test 101;;Oui;Automatisation;10;Lun,Mar,Mer,Jeu,Ven;07:00;15:30\n"
                "EMP-TEST-102;Technicien Test 102;;Non;Installation;;;;\n",
                encoding="utf-8",
            )
            rows = ResourceBootstrapFileSource(path).list_resources()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].sort_order, 10)
        assert rows[0].standard_schedule is not None
        self.assertEqual(rows[0].standard_schedule.weekdays, "Lun,Mar,Mer,Jeu,Ven")
        self.assertFalse(rows[1].active)
        self.assertIsNone(rows[1].standard_schedule)

    def test_xlsx_resources_sheet_is_supported(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "resources.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Ressources"
            sheet.append(HEADERS)
            sheet.append([
                "EMP-TEST-201", "Technicien Test 201", None, True,
                "Automatisation", 5, "Lun,Mar,Mer,Jeu,Ven", "08:00", "16:00",
            ])
            workbook.save(path)
            workbook.close()
            rows = ResourceBootstrapFileSource(path).list_resources()
        self.assertEqual(rows[0].external_id, "EMP-TEST-201")
        self.assertIsNotNone(rows[0].standard_schedule)

    def test_duplicate_external_id_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "resources.csv"
            path.write_text(
                "external_id,name,active,resource_class\n"
                "EMP-DUP,Ressource Test 1,true,Automatisation\n"
                "EMP-DUP,Ressource Test 2,true,Installation\n",
                encoding="utf-8",
            )
            with self.assertRaises(ApplicationOperationError) as raised:
                ResourceBootstrapFileSource(path).list_resources()
        self.assertEqual(raised.exception.code, "resource_bootstrap_duplicate_external_id")

    def test_partial_schedule_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "resources.csv"
            path.write_text(
                "external_id;name;active;resource_class;working_days;start_time;end_time\n"
                "EMP-PART;Ressource Test;true;Automatisation;Lun,Mar;07:00;\n",
                encoding="utf-8",
            )
            with self.assertRaises(ApplicationOperationError) as raised:
                ResourceBootstrapFileSource(path).list_resources()
        self.assertEqual(raised.exception.code, "resource_bootstrap_schedule_incomplete")

    def test_docker_importer_exposes_resource_tool(self) -> None:
        root = Path(__file__).resolve().parents[1]
        compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
        dockerfile = (root / "Dockerfile.importer").read_text(encoding="utf-8")
        self.assertIn("import-resources:", compose)
        self.assertIn('entrypoint: ["python", "tools/import_resources.py"]', compose)
        self.assertIn("tools/import_resources.py", dockerfile)


if __name__ == "__main__":
    unittest.main()
