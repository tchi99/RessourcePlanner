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

        result = DemandService(
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

    def test_failure_stops_following_workflow_steps(self) -> None:
        events: list[str] = []

        def fail(_repo: object, _number: str, _comment: str) -> None:
            events.append("approve")
            raise RuntimeError("approval failed")

        def sync(_repo: object, _number: str) -> None:
            events.append("sync")

        def rebuild(_repo: object):
            events.append("rebuild")
            return {}

        service = DemandService(
            object(),
            approve_record=fail,
            sync_approved_demand=sync,
            rebuild_planning=rebuild,
        )
        with self.assertRaisesRegex(RuntimeError, "approval failed"):
            service.approve("DMO-2")

        self.assertEqual(events, ["approve"])

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

    def test_approval_ui_crosses_demand_service_boundary(self) -> None:
        path = Path(__file__).resolve().parents[1] / "app" / "demand_service_ui.py"
        source = path.read_text(encoding="utf-8")

        self.assertIn("demand_service(self.repo).approve", source)
        self.assertNotIn("self.repo.approve_demand", source)

        names = [step.name for step in composition_manifest()]
        self.assertLess(names.index("planning_service_ui"), names.index("demand_service_ui"))
        self.assertLess(names.index("demand_service_ui"), names.index("communication_ui"))


if __name__ == "__main__":
    unittest.main()
