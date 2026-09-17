from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

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
