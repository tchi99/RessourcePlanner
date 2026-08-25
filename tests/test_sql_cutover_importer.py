from __future__ import annotations

import ast
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import unittest

from sqlalchemy import func, select

from app.infrastructure.migration import (
    CutoverImportError,
    extract_cutover_dataset,
    extract_demand_work_package_links,
    import_cutover_dataset,
)
from app.infrastructure.sql import (
    Base,
    Project,
    Resource,
    ResourceRequirement,
    Shift,
    WorkforceRequest,
    WorkforceRequestHistory,
    WorkPackage,
    create_session_factory,
    create_sql_engine,
    transactional_session,
)


ROOT = Path(__file__).resolve().parents[1]
IMPORTER = ROOT / "app" / "infrastructure" / "migration" / "sql_importer.py"
D1 = date(2026, 8, 24)


class _Reader:
    def __init__(self, rows: dict[str, list[dict]]) -> None:
        self.rows = rows

    def records(self, sheet: str, expected_header: str):
        return tuple(dict(row) for row in self.rows.get(sheet, []))


class SqlCutoverImporterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_sql_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.factory = create_session_factory(self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()

    def _rows(self) -> dict[str, list[dict]]:
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
                    "IDEffort": "EFF-2026-00001",
                    "N° projet": "5096",
                    "Précision": "Programmation PLC",
                    "Date de début": D1,
                    "Date de fin": D1,
                    "Efforts Prévus": 10,
                    "Status": "EN COURS",
                }
            ],
            "RessourcesMO": [
                {
                    "Technicien": "Alice",
                    "Classe": "Programmation",
                    "Competences": "PLC; SCADA",
                    "Note": "Senior",
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
                    "SourceEffortID": "EFF-2026-00001",
                    "DateCreation": datetime(2026, 8, 20, 9, 0),
                    "DateModification": datetime(2026, 8, 21, 10, 0),
                    "ApprouvePar": "Jean",
                    "DateApprobation": datetime(2026, 8, 21, 10, 0),
                }
            ],
            "Historique": [
                {
                    "Horodatage": datetime(2026, 8, 21, 10, 0),
                    "NoDemande": "DMO-2026-0001",
                    "Action": "Approbation",
                    "AncienStatut": "Soumise",
                    "NouveauStatut": "En planification",
                    "Utilisateur": "Jean",
                    "Commentaire": "OK",
                    "Details": "Validation PM",
                }
            ],
            "SegmentsMO": [
                {
                    "IDSegment": "SEG-2026-0001",
                    "NoDemande": "DMO-2026-0001",
                    "NumeroProjet": 5096,
                    "Technicien": "Alice",
                    "DateDebut": D1,
                    "DateFin": D1,
                    "HeuresPrevues": 8,
                    "Statut": "Planifié",
                    "SourceEffortRow": 2,
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
                    "IDAllocation": "MAN-LOCK",
                    "IDSegment": "SEG-2026-0001",
                    "Technicien": "Alice",
                    "Date": D1,
                    "Heures": 3,
                    "TypeAllocation": "Flexible",
                    "Verrouillee": "Oui",
                    "HorsHoraire": "Non",
                    "Note": "Décision conservée",
                },
                {
                    "IDAllocation": "AUTO-1",
                    "IDSegment": "SEG-2026-0001",
                    "Technicien": "Alice",
                    "Date": D1,
                    "Heures": 5,
                    "TypeAllocation": "Flexible",
                    "Verrouillee": "Non",
                    "HorsHoraire": "Non",
                },
                {
                    "IDAllocation": "MAN-QS",
                    "IDSegment": "SEG-QS",
                    "Technicien": "Alice",
                    "Date": D1,
                    "Heures": 2,
                    "TypeAllocation": "Fixe",
                    "Verrouillee": "Oui",
                    "HorsHoraire": "Non",
                },
            ],
        }

    def _source(self, rows: dict[str, list[dict]] | None = None):
        reader = _Reader(rows or self._rows())
        return (
            extract_cutover_dataset(reader),
            extract_demand_work_package_links(reader),
        )

    def test_full_import_preserves_legacy_ids_links_audit_and_locked_shifts(self) -> None:
        source, links = self._source()
        self.assertTrue(source.ok)

        with transactional_session(self.factory) as session:
            result = import_cutover_dataset(
                session,
                source,
                demand_work_package_links=links,
            )
            self.assertTrue(result.ok)
            self.assertEqual(result.source_counts, result.sql_counts)
            self.assertEqual(result.source_hours, result.sql_hours)

        with self.factory() as session:
            resource = session.scalar(select(Resource).where(Resource.name == "Alice"))
            assert resource is not None
            self.assertEqual(resource.resource_class, "Programmation")
            self.assertEqual(resource.competencies, "PLC; SCADA")
            self.assertEqual(resource.note, "Senior")
            self.assertEqual(resource.sort_order, 10)

            work_package = session.scalar(
                select(WorkPackage).where(
                    WorkPackage.legacy_effort_id == "EFF-2026-00001"
                )
            )
            assert work_package is not None
            request = session.scalar(
                select(WorkforceRequest).where(
                    WorkforceRequest.legacy_demand_number == "DMO-2026-0001"
                )
            )
            assert request is not None
            self.assertEqual(request.work_package_id, work_package.id)

            history = session.scalar(select(WorkforceRequestHistory))
            assert history is not None
            self.assertEqual(history.previous_status, "Soumise")
            self.assertEqual(history.status, "En planification")
            self.assertEqual(history.details, "Validation PM")

            normal = session.scalar(
                select(ResourceRequirement).where(
                    ResourceRequirement.legacy_segment_id == "SEG-2026-0001"
                )
            )
            quick = session.scalar(
                select(ResourceRequirement).where(
                    ResourceRequirement.legacy_segment_id == "SEG-QS"
                )
            )
            assert normal is not None and quick is not None
            self.assertEqual(normal.source_effort_id, "EFF-2026-00001")
            self.assertIsNotNone(normal.workforce_request_id)
            self.assertIsNone(quick.workforce_request_id)
            self.assertEqual(quick.origin, "QUICK_SHIFT")

            locked = session.scalars(
                select(Shift).where(Shift.locked.is_(True)).order_by(Shift.legacy_allocation_id)
            ).all()
            self.assertEqual(
                [(row.legacy_allocation_id, row.hours) for row in locked],
                [("MAN-LOCK", Decimal("3.00")), ("MAN-QS", Decimal("2.00"))],
            )
            self.assertEqual(
                int(session.scalar(select(func.count()).select_from(Shift)) or 0),
                3,
            )

    def test_historical_source_row_resolves_work_package_without_persisting_row_number(self) -> None:
        rows = self._rows()
        rows["DemandesMO"][0]["SourceEffortID"] = None
        rows["DemandesMO"][0]["SourceEffortRow"] = 2.0
        source, links = self._source(rows)
        self.assertEqual(links["DMO-2026-0001"], "2")

        with transactional_session(self.factory) as session:
            import_cutover_dataset(session, source, demand_work_package_links=links)
            request = session.scalar(select(WorkforceRequest))
            work_package = session.scalar(select(WorkPackage))
            assert request is not None and work_package is not None
            self.assertEqual(request.work_package_id, work_package.id)

    def test_non_empty_database_is_rejected_before_cutover_writes(self) -> None:
        source, links = self._source()
        with transactional_session(self.factory) as session:
            session.add(Project(id="EXISTING", number="EXISTING", name="Déjà là"))

        with self.assertRaises(CutoverImportError):
            with transactional_session(self.factory) as session:
                import_cutover_dataset(
                    session,
                    source,
                    demand_work_package_links=links,
                )

        with self.factory() as session:
            self.assertEqual(
                int(session.scalar(select(func.count()).select_from(Project)) or 0),
                1,
            )
            self.assertEqual(
                int(session.scalar(select(func.count()).select_from(Shift)) or 0),
                0,
            )

    def test_missing_history_timestamp_fails_closed_and_rolls_back_all_rows(self) -> None:
        rows = self._rows()
        rows["Historique"][0]["Horodatage"] = None
        source, links = self._source(rows)
        self.assertTrue(source.ok)

        with self.assertRaises(CutoverImportError):
            with transactional_session(self.factory) as session:
                import_cutover_dataset(
                    session,
                    source,
                    demand_work_package_links=links,
                )

        with self.factory() as session:
            for model in (Project, Resource, WorkPackage, WorkforceRequest, ResourceRequirement, Shift):
                self.assertEqual(
                    int(session.scalar(select(func.count()).select_from(model)) or 0),
                    0,
                )

    def test_blocking_preflight_is_rejected_without_sql_writes(self) -> None:
        rows = self._rows()
        rows["AllocationsMO"][0]["IDSegment"] = "SEG-UNKNOWN"
        source, links = self._source(rows)
        self.assertFalse(source.ok)

        with self.assertRaises(CutoverImportError):
            with transactional_session(self.factory) as session:
                import_cutover_dataset(
                    session,
                    source,
                    demand_work_package_links=links,
                )

        with self.factory() as session:
            self.assertEqual(
                int(session.scalar(select(func.count()).select_from(Project)) or 0),
                0,
            )

    def test_importer_is_transaction_neutral_and_does_not_rebuild_planning(self) -> None:
        source = IMPORTER.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")

        self.assertNotIn(".commit(", source)
        self.assertNotIn(".rollback(", source)
        self.assertNotIn("rebuild(", source)
        for forbidden in ("xlwings", "nicegui", "excel_repository", "planning_cutover"):
            self.assertFalse(
                any(forbidden in module for module in imports),
                f"cutover importer leaks forbidden dependency: {forbidden}",
            )


if __name__ == "__main__":
    unittest.main()
