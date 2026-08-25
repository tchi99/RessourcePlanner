from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date
from pathlib import Path
from types import SimpleNamespace
import ast
import unittest

from app.application import (
    ApplicationFacade,
    DemandApproveCommand,
    DemandCreateCommand,
    DemandSubmitCommand,
    DemandUpdateCommand,
    ManualAllocationCreateCommand,
    ManualAllocationDeleteCommand,
    ManualAllocationReleaseCommand,
    ManualAllocationUpdateCommand,
    PlanningRebuildCommand,
    PlanningResult,
    QuickShiftCreateCommand,
    SegmentAssignCommand,
    SegmentCancelCommand,
    SegmentCreateCommand,
    SegmentUpdateCommand,
)


DAY = date(2026, 8, 26)
ROOT = Path(__file__).resolve().parents[1]
APPLICATION = ROOT / "app" / "application"


class _Demands:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def create_command(self, command):
        self.calls.append(("create", command))
        return "DMO-42"

    def modify_command(self, command):
        self.calls.append(("update", command))
        return True

    def submit_command(self, command):
        self.calls.append(("submit", command))

    def approve_command(self, command):
        self.calls.append(("approve", command))
        return {
            "segments": "3",
            "allocations": 4,
            "locked_allocations": 1,
            "requested_hours": "24.5",
            "allocated_hours": 20,
            "overtime_hours": 2,
            "unallocated_hours": 4.5,
            "planning_engine": "pure",
            "performance": {"total_seconds": 0.25},
        }

    def request_correction_command(self, command):
        self.calls.append(("correction", command))

    def cancel_command(self, command):
        self.calls.append(("cancel", command))


class _Segments:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def create_command(self, command):
        self.calls.append(("create", command))
        return "SEG-42", {"allocated_hours": 8, "planning_engine": "pure"}

    def update_command(self, command):
        self.calls.append(("update", command))
        return {"allocated_hours": 7.5, "unallocated_hours": 0.5}

    def cancel_command(self, command):
        self.calls.append(("cancel", command))
        return {"allocated_hours": 0}


class _Allocations:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def create_manual_command(self, command):
        self.calls.append(("create", command))
        return "MAN-42"

    def update_manual_command(self, command):
        self.calls.append(("update", command))

    def release_manual_command(self, command):
        self.calls.append(("release", command))

    def delete_manual_command(self, command):
        self.calls.append(("delete", command))

    def assign_segment_command(self, command):
        self.calls.append(("assign", command))
        return {"allocated_hours": 6, "unallocated_hours": 2}


class _QuickShifts:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def create_command(self, command):
        self.calls.append(command)
        return SimpleNamespace(segment_id="SEG-QS", allocation_id="MAN-QS")


class _Planning:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def rebuild_command(self, command):
        self.calls.append(command)
        return {
            "segments": 2,
            "allocations": 3,
            "allocated_hours": 14,
            "unallocated_hours": 2,
            "planning_engine": "pure",
        }


def facade_fixture() -> tuple[ApplicationFacade, _Demands, _Segments, _Allocations, _QuickShifts, _Planning]:
    demands = _Demands()
    segments = _Segments()
    allocations = _Allocations()
    quick = _QuickShifts()
    planning = _Planning()
    facade = ApplicationFacade(
        demands=demands,  # type: ignore[arg-type]
        segments=segments,  # type: ignore[arg-type]
        allocations=allocations,  # type: ignore[arg-type]
        quick_shifts=quick,  # type: ignore[arg-type]
        planning=planning,  # type: ignore[arg-type]
    )
    return facade, demands, segments, allocations, quick, planning


class ApplicationFacadeTests(unittest.TestCase):
    def test_planning_result_normalizes_and_hides_adapter_diagnostics(self) -> None:
        result = PlanningResult.from_mapping(
            {
                "segments": "4",
                "allocations": 7,
                "allocated_hours": "18.5",
                "unallocated_hours": 1.5,
                "planning_engine": "pure",
                "performance": {"internal": True},
            }
        )

        self.assertEqual(result.segments, 4)
        self.assertEqual(result.allocated_hours, 18.5)
        self.assertEqual(result.engine, "pure")
        self.assertNotIn("performance", result.to_dict())
        with self.assertRaises(FrozenInstanceError):
            result.allocated_hours = 2  # type: ignore[misc]

    def test_demand_use_cases_return_stable_result_contracts(self) -> None:
        facade, demands, *_ = facade_fixture()

        created = facade.create_demand(
            DemandCreateCommand(project_number="P-1", desired_start=DAY, submit=True)
        )
        updated = facade.update_demand(
            DemandUpdateCommand(number="DMO-42", description="Nouvelle portée")
        )
        submitted = facade.submit_demand(DemandSubmitCommand("DMO-42"))
        approved = facade.approve_demand(DemandApproveCommand("DMO-42"))

        self.assertEqual(created.to_dict(), {
            "demand_number": "DMO-42",
            "status": "Soumise",
            "reapproval_required": False,
            "planning": None,
        })
        self.assertTrue(updated.reapproval_required)
        self.assertEqual(updated.status, "Soumise")
        self.assertEqual(submitted.status, "Soumise")
        self.assertEqual(approved.status, "En planification")
        self.assertEqual(approved.planning.allocated_hours, 20)  # type: ignore[union-attr]
        self.assertEqual(approved.planning.engine, "pure")  # type: ignore[union-attr]
        self.assertEqual([name for name, _ in demands.calls], ["create", "update", "submit", "approve"])

    def test_segment_allocation_quick_shift_and_rebuild_results_are_uniform(self) -> None:
        facade, _, segments, allocations, quick, planning = facade_fixture()

        segment = facade.create_segment(
            SegmentCreateCommand(
                demand_number="DMO-42",
                start_date=DAY,
                end_date=DAY,
                planned_hours=8,
            )
        )
        updated_segment = facade.update_segment(
            SegmentUpdateCommand(segment_id="SEG-42", planned_hours=7.5)
        )
        cancelled = facade.cancel_segment(SegmentCancelCommand("SEG-42"))
        assigned = facade.assign_segment(SegmentAssignCommand("SEG-42", "Alice"))
        allocation = facade.create_allocation(
            ManualAllocationCreateCommand("SEG-42", "Alice", DAY, 4)
        )
        updated_allocation = facade.update_allocation(
            ManualAllocationUpdateCommand("MAN-42", "Bob", DAY, 3)
        )
        released = facade.release_allocation(ManualAllocationReleaseCommand("MAN-42"))
        deleted = facade.delete_allocation(ManualAllocationDeleteCommand("MAN-42"))
        quick_result = facade.create_quick_shift(
            QuickShiftCreateCommand("P-1", "Alice", DAY, 2)
        )
        rebuild = facade.rebuild_planning(PlanningRebuildCommand())

        self.assertEqual(segment.segment_id, "SEG-42")
        self.assertEqual(segment.action, "created")
        self.assertEqual(updated_segment.action, "updated")
        self.assertEqual(cancelled.action, "cancelled")
        self.assertEqual(assigned.technician, "Alice")
        self.assertEqual(allocation.to_dict(), {"allocation_id": "MAN-42", "action": "created"})
        self.assertEqual(updated_allocation.action, "updated")
        self.assertEqual(released.action, "released")
        self.assertEqual(deleted.action, "deleted")
        self.assertEqual(quick_result.to_dict(), {"segment_id": "SEG-QS", "allocation_id": "MAN-QS"})
        self.assertEqual(rebuild.allocated_hours, 14)
        self.assertEqual(len(segments.calls), 3)
        self.assertEqual(len(allocations.calls), 5)
        self.assertEqual(len(quick.calls), 1)
        self.assertEqual(len(planning.calls), 1)

    def test_facade_and_results_are_transport_storage_neutral(self) -> None:
        forbidden = (
            "fastapi",
            "pydantic",
            "nicegui",
            "xlwings",
            "excel_repository",
            "sqlalchemy",
            "app.v13",
            "app.v14",
            "app.v15",
            "app.v16",
            "app.v17",
            "app.v18",
        )
        for filename in ("facade.py", "results.py"):
            source = (APPLICATION / filename).read_text(encoding="utf-8")
            tree = ast.parse(source)
            imports: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.append(node.module or "")
            for module in imports:
                self.assertFalse(
                    any(token in module for token in forbidden),
                    f"{filename} leaks transport/storage dependency: {module}",
                )


if __name__ == "__main__":
    unittest.main()
