from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from openpyxl import Workbook

from app.application import ApplicationOperationError
from app.infrastructure.erp_export import ErpTaskCatalogFileSource


HEADERS = [
    "Sélectionné",
    "ID tâche",
    "Description",
    "ID projet",
    "Statut",
    "Règle de facturation",
    "Règle de répartition",
    "Complété (%)",
    "Créé le",
    "Succursale",
    "Nom de l’employé",
    "CV",
    "Saisie des heures",
    "Dépenses",
]


class ErpTaskCatalogFileSourceTests(unittest.TestCase):
    def _xlsx(self, directory: str, rows: list[list[object]]) -> Path:
        path = Path(directory) / "Taches.xlsx"
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Données"
        sheet.append(HEADERS)
        for row in rows:
            sheet.append(row)
        workbook.save(path)
        workbook.close()
        return path

    def test_reads_real_export_shape_and_uses_project_plus_task_as_identity(self) -> None:
        with TemporaryDirectory() as directory:
            path = self._xlsx(
                directory,
                [
                    [
                        False,
                        210,
                        "AUTOMATISATION - APPEL DE SERVICE",
                        "M0612",
                        "Actif",
                        None,
                        None,
                        0,
                        None,
                        210,
                        None,
                        False,
                        True,
                        False,
                    ],
                    [
                        False,
                        210,
                        "ACHATS MATERIEL - AUTOMATISATION",
                        5176,
                        "Actif",
                        "REGLE-A",
                        "REPART-A",
                        0,
                        None,
                        210,
                        "Approbateur",
                        True,
                        True,
                        True,
                    ],
                ],
            )

            rows = ErpTaskCatalogFileSource(path).list_tasks()

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].external_key, ("M0612", "210"))
        self.assertEqual(rows[1].external_key, ("5176", "210"))
        self.assertEqual(rows[1].label, "ACHATS MATERIEL - AUTOMATISATION")
        self.assertTrue(rows[1].active)
        self.assertTrue(rows[1].time_entry_enabled)
        self.assertEqual(rows[1].branch, "210")

    def test_csv_is_supported(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "taches.csv"
            path.write_text(
                "ID tâche;Description;ID projet;Statut;Saisie des heures;Dépenses\n"
                "299;DIVERS ADMINISTRATION - AUTOMATISATION;5176;Inactif;Oui;Non\n",
                encoding="utf-8",
            )

            rows = ErpTaskCatalogFileSource(path).list_tasks()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].external_key, ("5176", "299"))
        self.assertFalse(rows[0].active)
        self.assertTrue(rows[0].time_entry_enabled)
        self.assertFalse(rows[0].expenses_enabled)

    def test_duplicate_composite_key_is_rejected(self) -> None:
        row = [
            False,
            "210",
            "Tâche A",
            "P-1",
            "Actif",
            None,
            None,
            0,
            None,
            None,
            None,
            None,
            True,
            False,
        ]
        with TemporaryDirectory() as directory:
            path = self._xlsx(directory, [row, row])
            with self.assertRaises(ApplicationOperationError) as raised:
                ErpTaskCatalogFileSource(path).list_tasks()

        self.assertEqual(raised.exception.code, "erp_task_catalog_duplicate_key")

    def test_missing_required_header_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "Taches.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Données"
            sheet.append(["ID tâche", "Description"])
            workbook.save(path)
            workbook.close()

            with self.assertRaises(ApplicationOperationError) as raised:
                ErpTaskCatalogFileSource(path).list_tasks()

        self.assertEqual(raised.exception.code, "erp_task_catalog_headers_invalid")


if __name__ == "__main__":
    unittest.main()
