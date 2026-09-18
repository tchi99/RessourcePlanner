from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from xml.etree import ElementTree
from zipfile import ZipFile

from openpyxl import Workbook

from app.application import ApplicationOperationError
from app.infrastructure.erp_export import ErpExcelProjectSource


HEADERS = [
    "Sélectionné",
    "ID projet",
    "Statut",
    "Date de début",
    "Description",
    "Nom du client",
    "Gestionnaire de projet",
    "Litige en cours",
    "Secteur d'activité",
    "Projet privé",
    "Autoriser les sorties à partir du stock libre",
]

_STYLES_PATH = "xl/styles.xml"
_SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


class ErpExcelProjectSourceTests(unittest.TestCase):
    def _workbook(self, directory: str, rows: list[list[object]], *, headers=HEADERS) -> Path:
        path = Path(directory) / "Projets.xlsx"
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Données"
        sheet.append(headers)
        for row in rows:
            sheet.append(row)
        workbook.save(path)
        workbook.close()
        return path

    def _make_first_fill_invalid(self, path: Path) -> None:
        patched = path.with_suffix(".patched.xlsx")
        with ZipFile(path, "r") as source, ZipFile(patched, "w") as target:
            root = ElementTree.fromstring(source.read(_STYLES_PATH))
            fills = root.find(f"{{{_SPREADSHEET_NS}}}fills")
            self.assertIsNotNone(fills)
            first_fill = list(fills)[0]
            for child in list(first_fill):
                first_fill.remove(child)

            ElementTree.register_namespace("", _SPREADSHEET_NS)
            styles = ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)

            for item in source.infolist():
                target.writestr(
                    item,
                    styles if item.filename == _STYLES_PATH else source.read(item.filename),
                )
        patched.replace(path)

    def test_reads_current_erp_export_shape_without_binding_external_id(self) -> None:
        with TemporaryDirectory() as directory:
            path = self._workbook(
                directory,
                [
                    [
                        False,
                        5182,
                        "Actif",
                        None,
                        "5182-EX: Projet test",
                        "Client A",
                        "Gestionnaire A",
                        False,
                        "B - Industriel",
                        False,
                        False,
                    ],
                    [
                        False,
                        "MAT0167",
                        "Actif",
                        None,
                        "MAT0167 - Véhicule",
                        "Client B",
                        None,
                        False,
                        "B - Industriel",
                        None,
                        False,
                    ],
                ],
            )

            rows = ErpExcelProjectSource(path).list_projects()

        self.assertEqual(len(rows), 2)
        self.assertIsNone(rows[0].external_id)
        self.assertEqual(rows[0].number, "5182")
        self.assertEqual(rows[0].name, "5182-EX: Projet test")
        self.assertEqual(rows[0].client, "Client A")
        self.assertEqual(rows[0].project_manager_name, "Gestionnaire A")
        self.assertEqual(rows[0].status, "Actif")
        self.assertEqual(rows[1].number, "MAT0167")
        self.assertIsNone(rows[1].project_manager_name)

    def test_tolerates_erp_export_with_empty_fill_style(self) -> None:
        with TemporaryDirectory() as directory:
            path = self._workbook(
                directory,
                [
                    [
                        False,
                        5182,
                        "Actif",
                        None,
                        "5182-EX: Projet test",
                        "Client A",
                        "Gestionnaire A",
                        False,
                        "B - Industriel",
                        False,
                        False,
                    ]
                ],
            )
            self._make_first_fill_invalid(path)

            rows = ErpExcelProjectSource(path).list_projects()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].number, "5182")
        self.assertEqual(rows[0].name, "5182-EX: Projet test")

    def test_missing_required_header_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            path = self._workbook(directory, [], headers=["ID projet", "Description"])
            with self.assertRaises(ApplicationOperationError) as raised:
                ErpExcelProjectSource(path).list_projects()
        self.assertEqual(raised.exception.code, "erp_excel_project_headers_invalid")

    def test_duplicate_project_number_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            row = [False, "P-1", "Actif", None, "Projet", "Client", None, False, None, False, False]
            path = self._workbook(directory, [row, row])
            with self.assertRaises(ApplicationOperationError) as raised:
                ErpExcelProjectSource(path).list_projects()
        self.assertEqual(raised.exception.code, "erp_excel_project_duplicate_number")


if __name__ == "__main__":
    unittest.main()
