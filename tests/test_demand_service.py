from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import patch

from app.application.demand_service import DemandService
from app.application.runtime_services import demand_service
from app.runtime_composition import composition_manifest


class DemandServiceTests(unittest.TestCase):
    @staticmethod
    def _service(repository: object, **overrides: object) -> DemandService[object]:
        def submit_record(_repo: object, _number: str) -> None:
            return None

        def approve_record(_repo: object, _number: str, _comment: str) -> None:
            return None

        def correction_record(_repo: object, _number: str, _comment: str) -> None:
            return None

        def cancel_record(_repo: object, _number: str) -> None:
            return None

        def sync(_repo: object, _number: str) -> None:
            return None

        def rebuild(_repo: object):
            return {}

        kwargs = {
            "submit_record": submit_record,
            "approve_record": approve_record,
            "request_correction_record": correction_record,
            "cancel_record": cancel_record,
            "sync_approved_demand": sync,
            "rebuild_planning": rebuild,
        }
        kwargs.update(overrides)
        return DemandService(repository, **kwargs)  # type: ignore[arg-type]

    def test_approve_orders_record_sync_rebuild_inside_one_batch(self) -> None:
        repository = object()
        events: list[object] = []

        @contextmanager
        def batch(repo: object, label: str):
            self.assertIs(repo, repository)
            events.append(("batch-enter", label))
            try:
                yield
            finally:
                events.append(("batch-exit", label))

        def approve_record(repo: object, number: str, comment: str) -> None:
            self.assertIs(repo, repository)
            events.append(("approve", number, comment))

        def sync(repo: object, number: str) -> None:
            self.assertIs(repo, repository)
            events.append(("sync", number))

        def rebuild(repo: object):
            self.assertIs(repo, repository)
            events.append(("rebuild",))
            return {"allocated_hours": 40.0, "engine": "pure"}

        result = self._service(
            repository,
            approve_record=approve_record,
            sync_approved_demand=sync,
            rebuild_planning=rebuild,
            batch=batch,
        ).approve("DMO-1", "ok")

        self.assertEqual(
            events,
            [
                ("batch-enter", "approve demand"),
                ("approve", "DMO-1", "ok"),
                ("sync", "DMO-1"),
                ("rebuild",),
                ("batch-exit", "approve demand"),
            ],
        )
        self.assertEqual(result, {"allocated_hours": 40.0, "engine": "pure"})
        self.assertIsInstance(result, dict)

    def test_failure_stops_following_approval_workflow_steps(self) -> None:
        events: list[str] = []

        def fail(_repo: object, _number: str, _comment: str) -> None:
            events.append("approve")
            raise RuntimeError("approval failed")

        def sync(_repo: object, _number: str) -> None:
            events.append("sync")

        def rebuild(_repo: object):
            events.append("rebuild")
            return {}

        service = self._service(
            object(),
            approve_record=fail,
            sync_approved_demand=sync,
            rebuild_planning=rebuild,
        )
        with self.assertRaisesRegex(RuntimeError, "approval failed"):
            service.approve("DMO-2")

        self.assertEqual(events, ["approve"])

    def test_simple_lifecycle_transitions_use_service_boundary(self) -> None:
        repository = object()
        events: list[object] = []

        @contextmanager
        def batch(_repo: object, label: str):
            events.append(("batch-enter", label))
            try:
                yield
            finally:
                events.append(("batch-exit", label))

        def submit(_repo: object, number: str) -> None:
            events.append(("submit", number))

        def correction(_repo: object, number: str, comment: str) -> None:
            events.append(("correction", number, comment))

        def cancel(_repo: object, number: str) -> None:
            events.append(("cancel", number))

        service = self._service(
            repository,
            submit_record=submit,
            request_correction_record=correction,
            cancel_record=cancel,
            batch=batch,
        )
        service.submit("DMO-10")
        service.request_correction("DMO-11", "  préciser la date  ")
        service.cancel("DMO-12")

        self.assertEqual(
            events,
            [
                ("batch-enter", "submit demand"),
                ("submit", "DMO-10"),
                ("batch-exit", "submit demand"),
                ("batch-enter", "request demand correction"),
                ("correction", "DMO-11", "préciser la date"),
                ("batch-exit", "request demand correction"),
                ("batch-enter", "cancel demand"),
                ("cancel", "DMO-12"),
                ("batch-exit", "cancel demand"),
            ],
        )

    def test_correction_reason_is_validated_in_service(self) -> None:
        called: list[str] = []

        def correction(_repo: object, _number: str, _comment: str) -> None:
            called.append("correction")

        service = self._service(object(), request_correction_record=correction)
        with self.assertRaisesRegex(ValueError, "commentaire de correction"):
            service.request_correction("DMO-20", "   ")
        self.assertEqual(called, [])

    def test_runtime_adapter_owns_approval_orchestration_and_rebuilds_once(self) -> None:
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

            def update_demand(
                self,
                number: str,
                updates: dict[str, object],
                *,
                action: str,
                comment: str,
            ) -> None:
                events.append(("update", number, updates, action, comment))

            def demands(self):
                return [{"NoDemande": "DMO-3", "Statut": "En planification"}]

        repository = FakeRepository()
        refinements = ModuleType("app.v15_refinements")
        engine = ModuleType("app.v15_engine")

        def sync(repo: object, demand: dict[str, object]) -> None:
            self.assertIs(repo, repository)
            events.append(("sync", demand["NoDemande"]))

        def rebuild(repo: object):
            self.assertIs(repo, repository)
            events.append(("rebuild",))
            return {"allocated_hours": 32.0}

        refinements._sync_segments_to_approved_demand = sync  # type: ignore[attr-defined]
        engine.rebuild_allocations = rebuild  # type: ignore[attr-defined]

        with patch.dict(
            sys.modules,
            {
                "app.v15_refinements": refinements,
                "app.v15_engine": engine,
            },
        ):
            result = demand_service(repository).approve("DMO-3", "approved")

        event_names = [event[0] for event in events]
        self.assertEqual(
            event_names,
            ["batch-enter", "update", "sync", "rebuild", "batch-exit"],
        )
        self.assertEqual(event_names.count("rebuild"), 1)
        update = events[1]
        self.assertEqual(update[1], "DMO-3")
        self.assertEqual(update[3], "Approbation")
        self.assertEqual(update[2]["Statut"], "En planification")
        self.assertEqual(update[2]["ApprouvePar"], "coordinator")
        self.assertEqual(result["allocated_hours"], 32.0)

    def test_runtime_simple_transitions_preserve_v1_status_and_audit_semantics(self) -> None:
        events: list[object] = []

        class FakeRepository:
            current_user = "coordinator"

            @contextmanager
            def batch_update(self, label: str):
                events.append(("batch", label))
                yield self

            def update_demand(
                self,
                number: str,
                updates: dict[str, object],
                *,
                action: str,
                comment: str,
            ) -> None:
                events.append((number, updates, action, comment))

        service = demand_service(FakeRepository())
        service.submit("DMO-30")
        service.request_correction("DMO-31", "Corriger les heures")
        service.cancel("DMO-32")

        writes = [event for event in events if isinstance(event, tuple) and str(event[0]).startswith("DMO-")]
        self.assertEqual(writes[0][1], {"Statut": "Soumise"})
        self.assertEqual(writes[0][2], "Soumission")
        self.assertEqual(writes[1][1]["Statut"], "À corriger")
        self.assertEqual(writes[1][1]["CommentaireApprobation"], "Corriger les heures")
        self.assertEqual(writes[1][2], "Retour pour correction")
        self.assertEqual(writes[2][1], {"Statut": "Annulée"})
        self.assertEqual(writes[2][2], "Annulation")

    def test_runtime_adapter_keeps_versioned_modules_lazy(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "application"
            / "runtime_services.py"
        )
        source = path.read_text(encoding="utf-8")

        self.assertNotIn("from .. import v15_refinements", source)
        self.assertNotIn("from .. import v15_engine", source)
        self.assertIn('import_module("app.v15_refinements")', source)
        self.assertIn('import_module("app.v15_engine")', source)

    def test_request_lifecycle_ui_crosses_demand_service_boundary(self) -> None:
        path = Path(__file__).resolve().parents[1] / "app" / "demand_service_ui.py"
        source = path.read_text(encoding="utf-8")

        for call in (
            "demand_service(self.repo).submit",
            "demand_service(self.repo).approve",
            "demand_service(self.repo).request_correction",
            "demand_service(self.repo).cancel",
        ):
            self.assertIn(call, source)

        for direct_repository_call in (
            "self.repo.submit_demand",
            "self.repo.approve_demand",
            "self.repo.request_correction",
            "self.repo.update_demand",
        ):
            self.assertNotIn(direct_repository_call, source)

        self.assertIn("PlannerUI.submit_request = _submit_request_via_service", source)
        self.assertIn("PlannerUI.cancel_request = _cancel_request_via_service", source)
        self.assertIn("PlannerUI.open_approval_dialog = _open_approval_dialog_via_service", source)
        self.assertIn("PlannerUI.open_correction_dialog = _open_correction_dialog_via_service", source)

        names = [step.name for step in composition_manifest()]
        self.assertLess(names.index("planning_service_ui"), names.index("demand_service_ui"))
        self.assertLess(names.index("demand_service_ui"), names.index("communication_ui"))

    def test_legacy_approval_wrappers_are_inventory_only_not_primary_ui_path(self) -> None:
        root = Path(__file__).resolve().parents[1]
        legacy_paths = [
            root / "app" / "v15.py",
            root / "app" / "v15_refinements.py",
            root / "app" / "v18_workflow_fixes.py",
        ]
        legacy_hits = {
            path.name: "ExcelRepository.approve_demand" in path.read_text(encoding="utf-8")
            for path in legacy_paths
        }
        self.assertEqual(
            legacy_hits,
            {
                "v15.py": True,
                "v15_refinements.py": True,
                "v18_workflow_fixes.py": False,
            },
        )
        service_ui = (root / "app" / "demand_service_ui.py").read_text(encoding="utf-8")
        self.assertNotIn("approve_demand", service_ui)


if __name__ == "__main__":
    unittest.main()
