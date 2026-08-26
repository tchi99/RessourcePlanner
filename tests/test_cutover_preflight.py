from __future__ import annotations

from datetime import date, datetime
import unittest

from app.infrastructure.migration.preflight import build_cutover_preflight


class _Reader:
    def __init__(self, rows):
        self.rows = rows

    def records(self, sheet: str, expected_header: str):
        return tuple(self.rows.get(sheet, ()))


def _valid_rows():
    return {
        "Liste des projets": (
            {"Numéro de Projet": "P-1", "Nom de référence": "Projet"},
        ),
        "Liste_Effort": (
            {
                "_row": 2,
                "N° projet": "P-1",
                "IDEffort": "EFF-1",
                "Précision": "Programmation",
                "Date de début": date(2026, 8, 25),
                "Date de fin": date(2026, 8, 25),
                "Efforts Prévus": 8,
            },
        ),
        "RessourcesMO": (
            {"Technicien": "Alice", "Classe": "Programmation"},
        ),
        "Disponibilites": (),
        "DemandesMO": (
            {
                "NoDemande": "DMO-1",
                "NumeroProjet": "P-1",
                "DateDebutSouhaitee": date(2026, 8, 25),
                "DateFinSouhaitee": date(2026, 8, 25),
                "NombreRessources": 1,
                "SourceEffortID": "EFF-1",
            },
        ),
        "Historique": (
            {
                "Horodatage": datetime(2026, 8, 25, 8, 0),
                "NoDemande": "DMO-1",
                "Action": "Création",
                "NouveauStatut": "Soumise",
            },
        ),
        "SegmentsMO": (
            {
                "IDSegment": "SEG-1",
                "NoDemande": "DMO-1",
                "NumeroProjet": "P-1",
                "Technicien": "Alice",
                "DateDebut": date(2026, 8, 25),
                "DateFin": date(2026, 8, 25),
                "HeuresPrevues": 8,
                "OrigineSegment": "REQUEST",
                "SourceEffortID": "EFF-1",
            },
        ),
        "AllocationsMO": (
            {
                "IDAllocation": "MAN-1",
                "IDSegment": "SEG-1",
                "Technicien": "Alice",
                "Date": date(2026, 8, 25),
                "Heures": 8,
                "Verrouillee": "Oui",
            },
        ),
    }


class CutoverPreflightTests(unittest.TestCase):
    def test_valid_work_package_links_are_accepted(self) -> None:
        preflight = build_cutover_preflight(_Reader(_valid_rows()))
        self.assertTrue(preflight.ok)
        self.assertEqual(preflight.demand_work_package_links["DMO-1"], "EFF-1")

    def test_unknown_work_package_link_is_blocking(self) -> None:
        rows = _valid_rows()
        rows["DemandesMO"][0]["SourceEffortID"] = "EFF-UNKNOWN"
        preflight = build_cutover_preflight(_Reader(rows))
        self.assertFalse(preflight.ok)
        codes = {item.code for item in preflight.report.blocking_errors}
        self.assertIn("unknown_source_effort", codes)

    def test_project_mismatch_between_demand_and_effort_is_blocking(self) -> None:
        rows = _valid_rows()
        rows["Liste des projets"] = (
            {"Numéro de Projet": "P-1", "Nom de référence": "Projet 1"},
            {"Numéro de Projet": "P-2", "Nom de référence": "Projet 2"},
        )
        rows["Liste_Effort"][0]["N° projet"] = "P-2"
        preflight = build_cutover_preflight(_Reader(rows))
        self.assertFalse(preflight.ok)
        codes = {item.code for item in preflight.report.blocking_errors}
        self.assertIn("source_effort_project_mismatch", codes)

    def test_missing_history_timestamp_is_promoted_to_blocking_error(self) -> None:
        rows = _valid_rows()
        rows["Historique"][0]["Horodatage"] = None
        preflight = build_cutover_preflight(_Reader(rows))
        self.assertFalse(preflight.ok)
        codes = {item.code for item in preflight.report.blocking_errors}
        self.assertIn("missing_history_timestamp", codes)
        self.assertNotIn("missing_timestamp", codes)


if __name__ == "__main__":
    unittest.main()
