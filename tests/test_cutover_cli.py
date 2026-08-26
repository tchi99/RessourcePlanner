from __future__ import annotations

from datetime import date, datetime, time
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from openpyxl import Workbook
from sqlalchemy import func, select

from app.infrastructure.migration.openpyxl_reader import OpenpyxlCutoverReader
from app.infrastructure.migration.preflight import build_cutover_preflight
from app.infrastructure.sql import (
    Shift,
    WorkforceRequest,
    create_session_factory,
    create_sql_engine,
)
from tools.cutover_excel_to_sql import run_cutover


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "cutover_excel_to_sql.py"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sheet(workbook: Workbook, name: str, headers: list[str], rows: list[list[object]]) -> None:
    worksheet = workbook.create_sheet(name)
    worksheet.append(headers)
    for row in rows:
        worksheet.append(row)


def _build_workbook(path: Path, *, history_timestamp: object = datetime(2026, 8, 25, 8, 0)) -> None:
    workbook = Workbook()
    workbook.remove(workbook.active)

    _sheet(
        workbook,
        "Liste des projets",
        ["Numéro de Projet", "Nom de référence", "Donneur d'ouvrage", "Chargé de projet", "État"],
        [["P-1", "Projet SQL", "Client", "Jean", "Actif"]],
    )
    _sheet(
        workbook,
        "Liste_Effort",
        [
            "N° projet",
            "IDEffort",
            "Précision",
            "Date de début",
            "Date de fin",
            "Efforts Prévus",
            "Status",
        ],
        [["P-1", "EFF-2026-00001", "Programmation", date(2026, 8, 25), date(2026, 8, 25), 8, "À FAIRE"]],
    )
    _sheet(
        workbook,
        "RessourcesMO",
        ["Technicien", "Classe", "Competences", "Note", "Ordre"],
        [["Alice", "Programmation", "PLC; SCADA", "Ressource test", 10]],
    )
    _sheet(
        workbook,
        "Disponibilites",
        [
            "ID",
            "Technicien",
            "Type",
            "DateDebut",
            "DateFin",
            "JoursSemaine",
            "HeureDebut",
            "HeureFin",
            "Note",
            "Actif",
        ],
        [["AV-1", "Alice", "Horaire standard", None, None, "Lun,Mar,Mer,Jeu,Ven", time(8, 0), time(16, 0), None, "Oui"]],
    )
    _sheet(
        workbook,
        "DemandesMO",
        [
            "NoDemande",
            "NumeroProjet",
            "Demandeur",
            "TypeDemande",
            "Priorite",
            "Confirmation",
            "DateDebutSouhaitee",
            "DateFinSouhaitee",
            "Description",
            "NombreRessources",
            "CompetencesRequises",
            "TempsEstimeHeures",
            "TechnicienPropose",
            "Statut",
            "DateCreation",
            "DateModification",
            "SourceEffortID",
        ],
        [[
            "DMO-2026-0001",
            "P-1",
            "Jean",
            "Projet",
            "Normale",
            "Confirmée",
            date(2026, 8, 25),
            date(2026, 8, 25),
            "Programmation",
            1,
            "PLC",
            8,
            "Alice",
            "En planification",
            datetime(2026, 8, 24, 9, 0),
            datetime(2026, 8, 24, 10, 0),
            "EFF-2026-00001",
        ]],
    )
    _sheet(
        workbook,
        "Historique",
        [
            "Horodatage",
            "NoDemande",
            "Action",
            "AncienStatut",
            "NouveauStatut",
            "Utilisateur",
            "Commentaire",
            "Details",
        ],
        [[history_timestamp, "DMO-2026-0001", "Approbation", "Soumise", "En planification", "Jean", "OK", "Audit V1"]],
    )
    _sheet(
        workbook,
        "SegmentsMO",
        [
            "IDSegment",
            "NoDemande",
            "NumeroProjet",
            "Technicien",
            "DateDebut",
            "DateFin",
            "HeuresPrevues",
            "Statut",
            "Description",
            "SourceEffortID",
            "CompetenceRequise",
            "TypePlanification",
            "Priorite",
            "HorsHoraireAutorise",
            "OrigineSegment",
        ],
        [[
            "SEG-2026-0001",
            "DMO-2026-0001",
            "P-1",
            "Alice",
            date(2026, 8, 25),
            date(2026, 8, 25),
            8,
            "Planifié",
            "Programmation",
            "EFF-2026-00001",
            "PLC",
            "Flexible",
            "Normale",
            "Non",
            "REQUEST",
        ]],
    )
    _sheet(
        workbook,
        "AllocationsMO",
        [
            "IDAllocation",
            "IDSegment",
            "Technicien",
            "Date",
            "Heures",
            "TypeAllocation",
            "Verrouillee",
            "HorsHoraire",
            "Confirmation",
            "Note",
        ],
        [["MAN-LOCK-1", "SEG-2026-0001", "Alice", date(2026, 8, 25), 8, "Flexible", "Oui", "Non", "Confirmée", "Décision manuelle"]],
    )
    workbook.save(path)
    workbook.close()


class CutoverCliTests(unittest.TestCase):
    def test_openpyxl_reader_and_preflight_are_read_only(self) -> None:
        with TemporaryDirectory() as directory:
            workbook_path = Path(directory) / "frozen.xlsx"
            _build_workbook(workbook_path)
            before = _sha256(workbook_path)

            with OpenpyxlCutoverReader(workbook_path) as reader:
                preflight = build_cutover_preflight(reader)

            self.assertTrue(preflight.ok)
            self.assertEqual(preflight.report.counts["demands"], 1)
            self.assertEqual(preflight.report.counts["locked_shifts"], 1)
            self.assertEqual(preflight.report.hours["locked_shift_total"], 8.0)
            self.assertEqual(_sha256(workbook_path), before)

    def test_dry_run_writes_report_without_modifying_workbook_or_sql(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workbook_path = root / "frozen.xlsx"
            report_path = root / "report.json"
            _build_workbook(workbook_path)
            before = _sha256(workbook_path)

            with patch.dict(os.environ, {"RESOURCEPLANNER_DATABASE_URL": ""}, clear=False):
                exit_code = run_cutover(
                    workbook=str(workbook_path),
                    report_path=report_path,
                    apply=False,
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(_sha256(workbook_path), before)
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["mode"], "dry-run")
            self.assertTrue(payload["preflight"]["ok"])
            self.assertTrue(payload["ready_for_apply"])
            self.assertNotIn("import", payload)
            self.assertNotIn("database_dialect", payload)

    def test_blocking_preflight_stops_before_database_access(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workbook_path = root / "invalid.xlsx"
            report_path = root / "blocked.json"
            _build_workbook(workbook_path, history_timestamp=None)
            database_path = root / "must-not-exist.db"

            with patch.dict(
                os.environ,
                {"RESOURCEPLANNER_DATABASE_URL": f"sqlite:///{database_path.as_posix()}"},
                clear=False,
            ):
                exit_code = run_cutover(
                    workbook=str(workbook_path),
                    report_path=report_path,
                    apply=True,
                )

            self.assertEqual(exit_code, 2)
            self.assertFalse(database_path.exists())
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertFalse(payload["preflight"]["ok"])
            codes = {row["code"] for row in payload["preflight"]["diagnostics"]}
            self.assertIn("missing_history_timestamp", codes)
            self.assertFalse(payload["ready_for_apply"])

    def test_apply_runs_migrations_and_imports_locked_shift_atomically(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workbook_path = root / "frozen.xlsx"
            report_path = root / "applied.json"
            database_path = root / "cutover.db"
            _build_workbook(workbook_path)
            before = _sha256(workbook_path)
            database_url = f"sqlite:///{database_path.as_posix()}"

            with patch.dict(
                os.environ,
                {"RESOURCEPLANNER_DATABASE_URL": database_url},
                clear=False,
            ):
                exit_code = run_cutover(
                    workbook=str(workbook_path),
                    report_path=report_path,
                    apply=True,
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(_sha256(workbook_path), before)
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertTrue(payload["applied"])
            self.assertTrue(payload["import"]["ok"])
            self.assertEqual(payload["database_dialect"], "sqlite")

            engine = create_sql_engine(database_url)
            try:
                factory = create_session_factory(engine)
                with factory() as session:
                    self.assertEqual(
                        int(session.scalar(select(func.count()).select_from(WorkforceRequest)) or 0),
                        1,
                    )
                    locked = session.scalar(
                        select(Shift).where(Shift.legacy_allocation_id == "MAN-LOCK-1")
                    )
                    self.assertIsNotNone(locked)
                    assert locked is not None
                    self.assertTrue(locked.locked)
                    self.assertEqual(float(locked.hours), 8.0)
            finally:
                engine.dispose()

    def test_script_can_be_invoked_directly_outside_repo_working_directory(self) -> None:
        with TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, str(TOOL), "--help"],
                cwd=directory,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--apply", result.stdout)
            self.assertIn("--workbook", result.stdout)


if __name__ == "__main__":
    unittest.main()
