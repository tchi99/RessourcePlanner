from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.application.demand_service import DemandService
from app.application.read_models import DemandReadModel, SegmentReadModel
from app.application.segment_service import SegmentService
from app.infrastructure.excel.demand_repository import ExcelDemandRepository
from app.infrastructure.excel.segment_repository import ExcelSegmentRepository


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


class RepositoryPortTests(unittest.TestCase):
    def test_demand_read_model_normalizes_storage_row(self) -> None:
        model = DemandReadModel.from_mapping(
            {
                "NoDemande": " DMO-10 ",
                "Statut": "En planification",
                "NumeroProjet": 1234,
                "NomProjet": "Projet A",
                "DateDebutSouhaitee": "2026-08-25",
                "DateFinSouhaitee": date(2026, 8, 29),
            }
        )

        self.assertEqual(model.number, "DMO-10")
        self.assertEqual(model.project_number, "1234")
        self.assertEqual(model.desired_start, date(2026, 8, 25))
        self.assertEqual(model.desired_end, date(2026, 8, 29))

    def test_segment_read_model_normalizes_storage_row(self) -> None:
        model = SegmentReadModel.from_mapping(
            {
                "IDSegment": "SEG-1",
                "NoDemande": "DMO-1",
                "NumeroProjet": "P-1",
                "Technicien": "Alex",
                "DateDebut": "2026-08-25",
                "DateFin": "2026-08-26",
                "HeuresPrevues": "7,5",
                "Statut": "Planifié",
                "OrigineSegment": "QUICK_SHIFT",
            }
        )

        self.assertEqual(model.segment_id, "SEG-1")
        self.assertEqual(model.planned_hours, 7.5)
        self.assertEqual(model.start_date, date(2026, 8, 25))
        self.assertEqual(model.origin, "QUICK_SHIFT")

    def test_demand_service_composes_against_repository_port(self) -> None:
        writes: list[tuple[object, ...]] = []

        class Port:
            def list(self):
                return ()

            def get(self, number: str):
                return DemandReadModel(number=number, status="En planification")

            def create(self, values, *, submit=False):
                writes.append(("create", dict(values), submit))
                return "DMO-NEW"

            def update(self, number, updates, *, action, comment=""):
                writes.append(("update", number, dict(updates), action, comment))

        events: list[object] = []
        context = object()
        service = DemandService.from_repository_port(
            context,
            Port(),
            current_user="coord@example.com",
            sync_approved_demand=lambda repo, number: events.append(("sync", repo, number)),
            rebuild_planning=lambda repo: {"engine": "pure"},
        )

        self.assertTrue(service.modify("DMO-1", {"Description": "révisée"}))
        service.approve("DMO-1", "ok")

        self.assertEqual(writes[0][0], "update")
        self.assertEqual(writes[0][2]["Statut"], "Soumise")
        approval = writes[1]
        self.assertEqual(approval[2]["Statut"], "En planification")
        self.assertEqual(approval[2]["ApprouvePar"], "coord@example.com")
        self.assertEqual(events, [("sync", context, "DMO-1")])

    def test_segment_service_composes_against_repository_port(self) -> None:
        writes: list[tuple[object, ...]] = []

        class Port:
            def list(self, *, include_cancelled=True):
                return ()

            def get(self, segment_id: str):
                return None

            def create(self, values):
                writes.append(("create", dict(values)))
                return "SEG-NEW"

            def update(self, segment_id, updates):
                writes.append(("update", segment_id, dict(updates)))

        service = SegmentService.from_repository_port(
            object(),
            Port(),
            rebuild_planning=lambda repo: {"engine": "pure"},
        )
        identifier, summary = service.create({"NoDemande": "DMO-1", "HeuresPrevues": 8})
        service.cancel(identifier)

        self.assertEqual(identifier, "SEG-NEW")
        self.assertEqual(summary["engine"], "pure")
        self.assertEqual(writes[-1], ("update", "SEG-NEW", {"Statut": "Annulé"}))

    def test_excel_demand_adapter_is_the_only_row_translation_boundary(self) -> None:
        class FakeExcel:
            def __init__(self):
                self.rows = [{"NoDemande": "DMO-1", "Statut": "Brouillon"}]
                self.writes: list[object] = []

            def demands(self):
                return list(self.rows)

            def create_demand(self, values, submit=False):
                self.writes.append(("create", values, submit))
                return "DMO-2"

            def update_demand(self, number, updates, *, action, comment):
                self.writes.append(("update", number, updates, action, comment))

        excel = FakeExcel()
        adapter = ExcelDemandRepository(excel)

        self.assertIsInstance(adapter.get("DMO-1"), DemandReadModel)
        self.assertEqual(adapter.create({"NumeroProjet": "P-1"}), "DMO-2")
        adapter.update("DMO-1", {"Statut": "Soumise"}, action="Soumission")
        self.assertEqual(excel.writes[-1][0], "update")

    def test_excel_segment_adapter_keeps_v1_modules_lazy(self) -> None:
        fake_v13 = SimpleNamespace(
            add_segment=lambda repo, values: "SEG-2",
            update_segment=lambda repo, identifier, values: None,
        )
        adapter = ExcelSegmentRepository(object())

        with patch(
            "app.infrastructure.excel.segment_repository.import_module",
            return_value=fake_v13,
        ):
            self.assertEqual(adapter.create({"NoDemande": "DMO-1"}), "SEG-2")
            adapter.update("SEG-2", {"Statut": "Annulé"})

    def test_application_repository_contracts_are_storage_neutral(self) -> None:
        for filename in (
            "application/read_models.py",
            "application/repository_ports.py",
            "application/demand_service.py",
            "application/segment_service.py",
        ):
            source = (APP / filename).read_text(encoding="utf-8").lower()
            for forbidden in ("xlwings", "sqlalchemy", "nicegui", "excel_repository"):
                self.assertNotIn(forbidden, source, f"{filename}: {forbidden}")

    def test_runtime_and_excel_adapters_remain_import_light(self) -> None:
        for filename in (
            "application/runtime_services.py",
            "infrastructure/excel/demand_repository.py",
            "infrastructure/excel/segment_repository.py",
        ):
            source = (APP / filename).read_text(encoding="utf-8").lower()
            self.assertNotIn("import xlwings", source, filename)
            self.assertNotIn("from ...excel_repository", source, filename)

        segment_source = (
            APP / "infrastructure" / "excel" / "segment_repository.py"
        ).read_text(encoding="utf-8")
        self.assertIn('import_module("app.segment_repository")', segment_source)
        self.assertIn('import_module("app.v13")', segment_source)

    def test_runtime_services_use_repository_ports_not_excel_rows(self) -> None:
        source = (APP / "application" / "runtime_services.py").read_text(encoding="utf-8")

        self.assertIn("ExcelDemandRepository(repository)", source)
        self.assertIn("ExcelSegmentRepository(repository)", source)
        self.assertIn("DemandService.from_repository_port(", source)
        self.assertIn("SegmentService.from_repository_port(", source)
        self.assertNotIn("repository.update_demand(", source)
        self.assertNotIn("repository.create_demand(", source)
        self.assertNotIn("for row in repository.demands()", source)


if __name__ == "__main__":
    unittest.main()
