from __future__ import annotations

from datetime import date
import unittest

from app.domain.planning_snapshot import PlanningSnapshot
from app.planning_cutover import (
    _assert_locked_allocations_preserved,
    _pure_persistence_rows,
)
from app.planning_shadow import build_shadow_report_from_snapshot


DAY = date(2026, 8, 25)


def locked_row(*, status: str = "Planifié") -> tuple[dict, dict]:
    segment = {
        "IDSegment": "S-LOCK",
        "Statut": status,
        "Technicien": "Tech A",
        "DateDebut": DAY,
        "DateFin": DAY,
        "HeuresPrevues": 8,
        "TypePlanification": "Flexible",
    }
    allocation = {
        "IDAllocation": "MAN-LOCK-1",
        "IDSegment": "S-LOCK",
        "Technicien": "Tech A",
        "Date": DAY,
        "Heures": 8,
        "TypeAllocation": "Flexible",
        "Verrouillee": "Oui",
        "HorsHoraire": "Non",
    }
    return segment, allocation


class LockedAllocationPersistenceTests(unittest.TestCase):
    def test_locked_row_survives_when_resource_is_temporarily_unschedulable(self) -> None:
        segment, allocation = locked_row()
        snapshot = PlanningSnapshot.capture(
            segments=[segment],
            demands=[],
            allocations=[allocation],
            availability=[],  # no standard schedule -> pure projection excludes the segment
            technicians=[{"name": "Tech A"}],
        )

        report = build_shadow_report_from_snapshot(snapshot)
        self.assertEqual(report.shadow_result.segment_count, 0)
        self.assertEqual(report.shadow_result.locked_allocation_count, 0)

        rows = _pure_persistence_rows(snapshot, report)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["IDAllocation"], "MAN-LOCK-1")
        self.assertEqual(rows[0]["Verrouillee"], "Oui")
        _assert_locked_allocations_preserved(snapshot, rows)

    def test_cancelled_segment_allows_locked_row_to_leave_rebuild_output(self) -> None:
        segment, allocation = locked_row(status="Annulé")
        snapshot = PlanningSnapshot.capture(
            segments=[segment],
            demands=[],
            allocations=[allocation],
            availability=[],
            technicians=[{"name": "Tech A"}],
        )
        report = build_shadow_report_from_snapshot(snapshot)

        rows = _pure_persistence_rows(snapshot, report)

        self.assertEqual(rows, [])
        _assert_locked_allocations_preserved(snapshot, rows)

    def test_guard_refuses_to_drop_active_locked_allocation(self) -> None:
        segment, allocation = locked_row()
        snapshot = PlanningSnapshot.capture(
            segments=[segment],
            demands=[],
            allocations=[allocation],
            availability=[],
            technicians=[{"name": "Tech A"}],
        )

        with self.assertRaises(RuntimeError) as ctx:
            _assert_locked_allocations_preserved(snapshot, [])

        self.assertIn("MAN-LOCK-1", str(ctx.exception))
        self.assertIn("Écriture annulée", str(ctx.exception))

    def test_malformed_active_locked_row_aborts_instead_of_being_deleted(self) -> None:
        segment, allocation = locked_row()
        allocation["Date"] = None
        snapshot = PlanningSnapshot.capture(
            segments=[segment],
            demands=[],
            allocations=[allocation],
            availability=[],
            technicians=[{"name": "Tech A"}],
        )
        report = build_shadow_report_from_snapshot(snapshot)

        with self.assertRaises(RuntimeError) as ctx:
            _pure_persistence_rows(snapshot, report)

        self.assertIn("allocation verrouillée active est invalide", str(ctx.exception))
        self.assertIn("MAN-LOCK-1", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
