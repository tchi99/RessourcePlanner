from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import patch

from app.application.demand_service import DemandService
from app.application.read_models import DemandReadModel
from app.application.runtime_services import demand_service


class _Demands:
    def __init__(self, record: DemandReadModel | None = None, events=None) -> None:
        self.record = record
        self.events = events if events is not None else []
        self.next_number = "DMO-NEW"

    def list(self):
        return (self.record,) if self.record is not None else ()

    def get(self, number):
        if self.record is not None and self.record.number == number:
            return self.record
        return None

    def create(self, values, *, submit=False):
        self.events.append(("create", dict(values), submit))
        return self.next_number

    def update(self, number, updates, *, action, comment=""):
        self.events.append(("update", number, dict(updates), action, comment))


class _Planning:
    def __init__(self, events, failure: Exception | None = None) -> None:
        self.events = events
        self.failure = failure

    def rebuild(self):
        self.events.append(("rebuild",))
        if self.failure is not None:
            raise self.failure
        return {"allocated_hours": 40.0, "engine": "pure"}


class _Sync:
    def __init__(self, events, failure: Exception | None = None) -> None:
        self.events = events
        self.failure = failure

    def sync_approved(self, number):
        self.events.append(("sync", number))
        if self.failure is not None:
            raise self.failure


class DemandServiceTests(unittest.TestCase):
    @staticmethod
    def _service(
        *,
        record: DemandReadModel | None = None,
        events=None,
        current_user="coordinator",
        batch=None,
        sync_failure=None,
        planning_failure=None,
    ):
        events = events if events is not None else []
        demands = _Demands(record, events)
        return (
            DemandService(
                demands,
                _Planning(events, planning_failure),
                _Sync(events, sync_failure),
                current_user=current_user,
                batch=batch,
            ),
            demands,
            events,
        )

    def test_create_strips_workflow_fields_and_validates_required_data(self) -> None:
        service, _demands, events = self._service()

        number = service.create(
            {
                "NumeroProjet": "5094",
                "DateDebutSouhaitee": "2026-08-25",
                "Description": "Travail",
                "Statut": "En planification",
                "NoDemande": "FORBIDDEN",
                "ApprouvePar": "x",
            },
            submit=True,
        )

        self.assertEqual(number, "DMO-NEW")
        payload = events[0][1]
        self.assertNotIn("Statut", payload)
        self.assertNotIn("NoDemande", payload)
        self.assertNotIn("ApprouvePar", payload)
        self.assertTrue(events[0][2])

        with self.assertRaises(ValueError):
            service.create({"NumeroProjet": "", "DateDebutSouhaitee": "2026-08-25"})
        with self.assertRaises(ValueError):
            service.create({"NumeroProjet": "5094"})

    def test_modify_approved_business_demand_requires_reapproval_without_touching_plan(self) -> None:
        events: list[object] = []

        @contextmanager
        def batch(label: str):
            events.append(("batch-enter", label))
            try:
                yield
            finally:
                events.append(("batch-exit", label))

        service, _demands, _ = self._service(
            record=DemandReadModel(number="DMO-EDIT", status="En planification"),
            events=events,
            batch=batch,
        )
        required = service.modify(
            "DMO-EDIT",
            {"Description": "Nouvelle portée", "Confirmation": "Tentative"},
            "Demande modifiée dans l'application",
        )

        self.assertTrue(required)
        self.assertEqual(events[0], ("batch-enter", "modify demand"))
        self.assertEqual(events[-1], ("batch-exit", "modify demand"))
        write = events[1]
        self.assertEqual(write[0], "update")
        updates = write[2]
        self.assertEqual(updates["Statut"], "Soumise")
        self.assertIsNone(updates["ApprouvePar"])
        self.assertIsNone(updates["DateApprobation"])
        self.assertIn("nouvelle approbation requise", updates["CommentaireApprobation"])
        self.assertIn("planification existante est conservée", write[4])
        self.assertFalse(any(event[0] in {"sync", "rebuild"} for event in events if isinstance(event, tuple)))

    def test_modify_unapproved_demand_does_not_force_reapproval(self) -> None:
        service, _demands, events = self._service(
            record=DemandReadModel(number="DMO-DRAFT", status="Brouillon")
        )

        required = service.modify(
            "DMO-DRAFT",
            {"Description": "Brouillon modifié"},
            "Modification",
        )

        self.assertFalse(required)
        self.assertEqual(events[0][2], {"Description": "Brouillon modifié"})

    def test_modify_unknown_demand_fails_before_write(self) -> None:
        service, _demands, events = self._service(record=None)
        with self.assertRaisesRegex(KeyError, "DMO-MISSING"):
            service.modify("DMO-MISSING", {"Description": "x"})
        self.assertEqual(events, [])

    def test_approve_orders_record_sync_rebuild_inside_one_batch(self) -> None:
        events: list[object] = []

        @contextmanager
        def batch(label: str):
            events.append(("batch-enter", label))
            try:
                yield
            finally:
                events.append(("batch-exit", label))

        service, _demands, _ = self._service(events=events, batch=batch)
        result = service.approve("DMO-1", "ok")

        self.assertEqual(
            [event[0] for event in events],
            ["batch-enter", "update", "sync", "rebuild", "batch-exit"],
        )
        update = events[1]
        self.assertEqual(update[2]["Statut"], "En planification")
        self.assertEqual(update[2]["ApprouvePar"], "coordinator")
        self.assertEqual(update[3], "Approbation")
        self.assertEqual(result["allocated_hours"], 40.0)

    def test_sync_failure_stops_rebuild(self) -> None:
        events: list[object] = []
        service, _demands, _ = self._service(
            events=events,
            sync_failure=RuntimeError("sync failed"),
        )

        with self.assertRaisesRegex(RuntimeError, "sync failed"):
            service.approve("DMO-2")

        self.assertEqual([event[0] for event in events], ["update", "sync"])

    def test_simple_lifecycle_transitions_preserve_status_and_audit_semantics(self) -> None:
        service, _demands, events = self._service()
        service.submit("DMO-10")
        service.request_correction("DMO-11", "  préciser la date  ")
        service.cancel("DMO-12")

        self.assertEqual(events[0][2], {"Statut": "Soumise"})
        self.assertEqual(events[0][3], "Soumission")
        self.assertEqual(events[1][2]["Statut"], "À corriger")
        self.assertEqual(events[1][2]["CommentaireApprobation"], "préciser la date")
        self.assertEqual(events[1][3], "Retour pour correction")
        self.assertEqual(events[2][2], {"Statut": "Annulée"})
        self.assertEqual(events[2][3], "Annulation")

    def test_correction_reason_is_validated_before_repository(self) -> None:
        service, _demands, events = self._service()
        with self.assertRaisesRegex(ValueError, "commentaire de correction"):
            service.request_correction("DMO-20", "   ")
        self.assertEqual(events, [])

    def test_runtime_adapter_uses_excel_command_adapters_and_rebuilds_once(self) -> None:
        events: list[object] = []

        class FakeRepository:
            current_user = "coordinator"

            @contextmanager
            def batch_update(self, label: str):
                events.append(("batch-enter", label))
                try:
                    yield self
                finally:
                    events.append(("batch-exit", label))

            def update_demand(self, number, updates, *, action, comment):
                events.append(("update", number, updates, action, comment))

            def demands(self):
                return [{"NoDemande": "DMO-3", "Statut": "En planification"}]

        repository = FakeRepository()
        refinements = ModuleType("app.v15_refinements")
        engine = ModuleType("app.v15_engine")

        def sync(repo, demand):
            self.assertIs(repo, repository)
            events.append(("sync", demand["NoDemande"]))

        def rebuild(repo):
            self.assertIs(repo, repository)
            events.append(("rebuild",))
            return {"allocated_hours": 32.0}

        refinements._sync_segments_to_approved_demand = sync  # type: ignore[attr-defined]
        engine.rebuild_allocations = rebuild  # type: ignore[attr-defined]

        with patch.dict(
            sys.modules,
            {"app.v15_refinements": refinements, "app.v15_engine": engine},
        ):
            result = demand_service(repository).approve("DMO-3", "approved")

        self.assertEqual(
            [event[0] for event in events],
            ["batch-enter", "update", "sync", "rebuild", "batch-exit"],
        )
        self.assertEqual(result["allocated_hours"], 32.0)

    def test_application_service_has_only_port_dependencies(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "application"
            / "demand_service.py"
        ).read_text(encoding="utf-8")
        for token in (
            "nicegui",
            "xlwings",
            "excel_repository",
            "v15_engine",
            "v15_refinements",
            "repository_context",
            "sync_approved_demand: Callable",
            "rebuild_planning: Callable",
        ):
            self.assertNotIn(token, source)
        self.assertIn("DemandRepositoryPort", source)
        self.assertIn("PlanningCommandPort", source)
        self.assertIn("ApprovedDemandSyncPort", source)


if __name__ == "__main__":
    unittest.main()
