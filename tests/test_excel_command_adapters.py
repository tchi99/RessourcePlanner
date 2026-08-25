from __future__ import annotations

import sys
from types import ModuleType
import unittest
from unittest.mock import patch

from app.infrastructure.excel import command_adapters as adapters


class ExcelCommandAdapterTests(unittest.TestCase):
    def tearDown(self) -> None:
        adapters._captured_allocation_functions = None

    def test_allocation_capture_keeps_original_functions_after_entrypoint_replacement(self) -> None:
        repository = object()
        calls: list[tuple] = []
        engine = ModuleType("app.v15_engine")
        v16 = ModuleType("app.v16")

        def create(repo, segment, tech, day, hours, overtime=False, note=""):
            calls.append(("captured-create", repo, segment, tech, day, hours, overtime, note))
            return "MAN-1"

        def update(*args):
            calls.append(("captured-update", *args))

        def release(*args):
            calls.append(("captured-release", *args))

        def delete(*args):
            calls.append(("captured-delete", *args))

        engine.create_manual_allocation = create  # type: ignore[attr-defined]
        engine.update_manual_allocation = update  # type: ignore[attr-defined]
        engine.release_manual_allocation = release  # type: ignore[attr-defined]
        engine.delete_manual_allocation = delete  # type: ignore[attr-defined]
        engine.rebuild_allocations = lambda _repo: {}  # type: ignore[attr-defined]

        with patch.dict(sys.modules, {"app.v15_engine": engine, "app.v16": v16}):
            adapters.capture_excel_allocation_commands()
            adapters.install_excel_allocation_service_entrypoints(
                create_manual=lambda *_args: "WRAPPED",
                update_manual=lambda *_args: None,
                release_manual=lambda *_args: None,
                delete_manual=lambda *_args: None,
                assign_segment=lambda *_args: None,
            )
            commands = adapters.excel_allocation_commands(repository)
            identifier = commands.create_manual("SEG-1", "Alice", "2026-08-25", 4, True, "note")

        self.assertEqual(identifier, "MAN-1")
        self.assertEqual(calls[0][0], "captured-create")
        self.assertIs(calls[0][1], repository)

    def test_planning_adapter_resolves_active_engine_alias_each_call(self) -> None:
        repository = object()
        engine = ModuleType("app.v15_engine")
        calls: list[str] = []

        def rebuild(repo):
            self.assertIs(repo, repository)
            calls.append("pure")
            return {"engine": "pure"}

        engine.rebuild_allocations = rebuild  # type: ignore[attr-defined]
        with patch.dict(sys.modules, {"app.v15_engine": engine}):
            result = adapters.ExcelPlanningCommandAdapter(repository).rebuild()

        self.assertEqual(result["engine"], "pure")
        self.assertEqual(calls, ["pure"])

    def test_approved_demand_sync_keeps_raw_excel_mapping_inside_adapter(self) -> None:
        repository = object()
        refinements = ModuleType("app.v15_refinements")
        events: list[tuple] = []

        class Demands:
            def raw_mapping(self, number):
                return {"NoDemande": number, "Statut": "En planification"}

        def sync(repo, demand):
            events.append((repo, demand["NoDemande"]))

        refinements._sync_segments_to_approved_demand = sync  # type: ignore[attr-defined]
        with patch.dict(sys.modules, {"app.v15_refinements": refinements}):
            adapter = adapters.ExcelApprovedDemandSyncAdapter(repository, Demands())  # type: ignore[arg-type]
            adapter.sync_approved("DMO-1")

        self.assertEqual(events, [(repository, "DMO-1")])


if __name__ == "__main__":
    unittest.main()
