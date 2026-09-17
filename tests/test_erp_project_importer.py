from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from openpyxl import Workbook
from sqlalchemy import func, select

from app.infrastructure.sql import Base, Project, create_session_factory, create_sql_engine
from tools.import_erp_projects import synchronize_file


class ErpProjectImporterTests(unittest.TestCase):
    def _workbook(self, directory: str) -> Path:
        path = Path(directory) / "Projets.xlsx"
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Données"
        sheet.append(
            [
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
        )
        sheet.append(
            [
                False,
                "P-100",
                "Actif",
                None,
                "Projet importé",
                "Client A",
                "Gestionnaire A",
                False,
                "B - Industriel",
                False,
                False,
            ]
        )
        workbook.save(path)
        workbook.close()
        return path

    def test_preview_rolls_back_and_apply_commits(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "resourceplanner.db"
            database_url = f"sqlite:///{database_path.as_posix()}"
            engine = create_sql_engine(database_url)
            Base.metadata.create_all(engine)
            factory = create_session_factory(engine)
            engine.dispose()
            xlsx = self._workbook(directory)

            preview = synchronize_file(xlsx, database_url=database_url, apply=False)
            self.assertEqual((preview.created, preview.updated, preview.unchanged), (1, 0, 0))
            with factory() as session:
                self.assertEqual(session.scalar(select(func.count()).select_from(Project)), 0)

            applied = synchronize_file(xlsx, database_url=database_url, apply=True)
            self.assertEqual((applied.created, applied.updated, applied.unchanged), (1, 0, 0))
            with factory() as session:
                rows = session.scalars(select(Project)).all()
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0].number, "P-100")
                self.assertIsNone(rows[0].erp_external_id)


if __name__ == "__main__":
    unittest.main()
