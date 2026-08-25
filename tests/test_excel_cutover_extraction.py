from __future__ import annotations

import ast
from datetime import date, datetime
from pathlib import Path
import unittest

from app.infrastructure.migration import extract_cutover_dataset


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "app" / "infrastructure" / "migration" / "excel_cutover.py"
D1 = date(2026, 8, 24)


class _Reader:
    def __init__(self, rows: dict[str, list[dict]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, str]] = []

    def records(self, sheet: str, expected_header: str):
        self.calls.append((sheet, expected_header))
        return tuple(dict(row) for row in self.rows.get(sheet, []))


class ExcelCutoverExtractionTests(unittest.TestCase):
    def _valid_rows(self) -> dict[str, list[dict]]:
        return {
            "Liste des projets": [
                {
                    "Numéro de Projet": 5096.0,
                    "Nom de référence": "Projet A",
                    "Donneur d'ouvrage": "Client A",
                    "Chargé de projet": "CP A",
                    "État": "Actif",
                }
            ],
            "Liste_Effort": [
                {
                    "_row": 2,
                    "IDEffort": "EFF-1",
                    "N° projet": "5096",
                    "Précision": "Programmation",
                    "Date de début": D1,
                    "Date de fin": D1,
                    "Efforts Prévus": 8,
                    "Status": "EN COURS",
                }
            ],
            "RessourcesMO": [
                {
                    "Technicien": "Alice",
                    "Classe": "Programmation",
                    "Competences": "PLC",
                    "Ordre": 10,
                }
            ],
            "Disponibilites": [
                {
                    "ID": "STD-A",
                    "Technicien": "Alice",
                    "Type": "Horaire standard",
                    "JoursSemaine": "Lun,Mar,Mer,Jeu,Ven",
                    "HeureDebut": "08:00",
                    "HeureFin": "16:00",
                    "Actif": "Oui",
                }
            ],
            "DemandesMO": [
                {
                    "NoDemande": "DMO-2026-0001",
                    "NumeroProjet": 5096,
                    "Demandeur": "Jean",
                    "DateDebutSouhaitee": D1,
                    "DateFinSouhaitee": D1,
                    "NombreRessources": 1,
                    "TempsEstimeHeures": 8,
                    "TechnicienPropose": "Alice",
                    "Statut": "En planification",
                }
            ],
            "Historique": [
                {
                    "Horodatage": datetime(2026, 8, 24, 8, 0),
                    "NoDemande": "DMO-2026-0001",
                    "Action": "Approbation",
                    "NouveauStatut": "En planification",
                    "Utilisateur": "Jean",
                }
            ],
            "SegmentsMO": [
                {
                    "IDSegment": "SEG-1",
                    "NoDemande": "DMO-2026-0001",
                    "NumeroProjet": "5096.0",
                    "Technicien": "Alice",
                    "DateDebut": D1,
                    "DateFin": D1,
                    "HeuresPrevues": 8,
                    "Statut": "Planifié",
                    "TypePlanification": "Flexible",
                    "OrigineSegment": "REQUEST",
                },
                {
                    "IDSegment": "SEG-QS",
                    "NoDemande": None,
                    "NumeroProjet": 5096,
                    "Technicien": "Alice",
                    "DateDebut": D1,
                    "DateFin": D1,
                    "HeuresPrevues": 2,
                    "Statut": "Planifié",
                    "TypePlanification": "Fixe",
                    "OrigineSegment": "QUICK_SHIFT",
                },
            ],
            "AllocationsMO": [
                {
                    "IDAllocation": "MAN-1",
                    "IDSegment": "SEG-1",
                    "Technicien": "Alice",
                    "Date": D1,
                    "Heures": 3,
                    "TypeAllocation": "Flexible",
                    "Verrouillee": "Oui",
                    "HorsHoraire": "Non",
                },
                {
                    "IDAllocation": "MAN-QS",
                    "IDSegment": "SEG-QS",
                    "Technicien": "Alice",
                    "Date": D1,
                    "Heures": 2,
                    "TypeAllocation": "Fixe",
                    "Verrouillee": True,
                    "HorsHoraire": False,
                },
            ],
        }

    def test_valid_dataset_is_normalized_and_reconciled_without_writes(self) -> None:
        reader = _Reader(self._valid_rows())
        report = extract_cutover_dataset(reader)

        self.assertTrue(report.ok, [row.as_dict() for row in report.diagnostics])
        self.assertEqual(report.counts["projects"], 1)
        self.assertEqual(report.counts["requirements"], 2)
        self.assertEqual(report.counts["locked_shifts"], 2)
        self.assertEqual(report.hours["requirement_planned"], 10.0)
        self.assertEqual(report.hours["locked_shift_total"], 5.0)
        self.assertEqual(report.dataset.projects[0]["number"], "5096")
        self.assertEqual(report.dataset.demands[0]["project_number"], "5096")
        self.assertEqual(report.dataset.requirements[0]["project_number"], "5096")
        self.assertEqual(report.dataset.requirements[1]["origin"], "QUICK_SHIFT")
        self.assertIsNone(report.dataset.requirements[1]["demand_number"])
        self.assertEqual(len(reader.calls), 8)
        self.assertEqual(
            {sheet for sheet, _header in reader.calls},
            {
                "Liste des projets",
                "Liste_Effort",
                "RessourcesMO",
                "Disponibilites",
                "DemandesMO",
                "Historique",
                "SegmentsMO",
                "AllocationsMO",
            },
        )

    def test_broken_references_duplicates_and_fake_quick_shift_are_blocking(self) -> None:
        rows = self._valid_rows()
        rows["DemandesMO"].append(dict(rows["DemandesMO"][0]))
        rows["SegmentsMO"][1]["NoDemande"] = "DMO-2026-0001"
        rows["AllocationsMO"][0]["Technicien"] = "Inconnu"
        rows["AllocationsMO"].append(
            {
                "IDAllocation": "A-ORPHAN",
                "IDSegment": "SEG-MISSING",
                "Technicien": "Alice",
                "Date": D1,
                "Heures": 1,
            }
        )

        report = extract_cutover_dataset(_Reader(rows))
        codes = {row.code for row in report.blocking_errors}

        self.assertFalse(report.ok)
        self.assertIn("duplicate_legacy_id", codes)
        self.assertIn("adhoc_has_fake_demand", codes)
        self.assertIn("unknown_resource", codes)
        self.assertIn("unknown_requirement", codes)

    def test_global_holiday_without_resource_is_valid_but_other_global_rule_is_not(self) -> None:
        rows = self._valid_rows()
        rows["Disponibilites"].extend(
            [
                {
                    "ID": "HOLIDAY",
                    "Technicien": "",
                    "Type": "Jour férié",
                    "DateDebut": D1,
                    "DateFin": D1,
                    "Actif": "Oui",
                },
                {
                    "ID": "BAD-GLOBAL",
                    "Technicien": "",
                    "Type": "Vacances",
                    "DateDebut": D1,
                    "DateFin": D1,
                    "Actif": "Oui",
                },
            ]
        )

        report = extract_cutover_dataset(_Reader(rows))
        errors = [row for row in report.blocking_errors if row.entity == "availability"]
        self.assertEqual([row.identifier for row in errors], ["BAD-GLOBAL"])
        self.assertEqual(errors[0].code, "missing_resource")

    def test_extractor_core_has_no_excel_sql_or_ui_dependency(self) -> None:
        source = MODULE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")

        for forbidden in ("xlwings", "sqlalchemy", "nicegui", "excel_repository"):
            self.assertFalse(
                any(forbidden in module for module in imports),
                f"cutover extractor leaks dependency: {forbidden}",
            )
        self.assertNotIn(".save(", source)
        self.assertNotIn(".commit(", source)


if __name__ == "__main__":
    unittest.main()
