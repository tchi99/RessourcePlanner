from __future__ import annotations

import unittest
from datetime import date

from app.domain.planning_engine import (
    LockedAllocationInput,
    SegmentInput,
    build_allocation_plan,
)


D1 = date(2026, 8, 17)
D2 = date(2026, 8, 18)


class PlanningEngineTests(unittest.TestCase):
    def test_locked_allocation_is_preserved_and_subtracted_from_segment(self) -> None:
        result = build_allocation_plan(
            [SegmentInput("S1", "R1", D1, D1, 8, "Fixe")],
            [LockedAllocationInput("S1", "R1", D1, 3)],
            {("R1", D1): 8},
        )
        self.assertEqual(result.locked_allocation_count, 1)
        self.assertEqual(result.allocated_hours, 8)
        locked = [row for row in result.allocations if row.locked]
        automatic = [row for row in result.allocations if not row.locked]
        self.assertEqual(locked[0].hours, 3)
        self.assertEqual(automatic[0].hours, 5)

    def test_fixed_segment_can_overload_standard_capacity(self) -> None:
        result = build_allocation_plan(
            [SegmentInput("S1", "R1", D1, D1, 12, "Fixe")],
            [],
            {("R1", D1): 8},
        )
        self.assertEqual(result.allocated_hours, 12)
        self.assertEqual(result.unallocated_hours, 0)
        self.assertEqual(result.allocations[0].hours, 12)

    def test_flexible_segment_leaves_shortage_unallocated(self) -> None:
        result = build_allocation_plan(
            [SegmentInput("S1", "R1", D1, D1, 12, "Flexible")],
            [],
            {("R1", D1): 8},
        )
        self.assertEqual(result.allocated_hours, 8)
        self.assertEqual(result.unallocated_hours, 4)

    def test_fixed_work_consumes_capacity_before_flexible_work(self) -> None:
        result = build_allocation_plan(
            [
                SegmentInput("FIX", "R1", D1, D1, 6, "Fixe"),
                SegmentInput("FLEX", "R1", D1, D1, 6, "Flexible"),
            ],
            [],
            {("R1", D1): 8},
        )
        hours = {row.segment_id: row.hours for row in result.allocations}
        self.assertEqual(hours["FIX"], 6)
        self.assertEqual(hours["FLEX"], 2)
        self.assertEqual(result.unallocated_hours, 4)

    def test_priority_orders_competing_flexible_segments(self) -> None:
        result = build_allocation_plan(
            [
                SegmentInput("NORMAL", "R1", D1, D1, 6, "Flexible", priority_rank=2),
                SegmentInput("URGENT", "R1", D1, D1, 6, "Flexible", priority_rank=0),
            ],
            [],
            {("R1", D1): 8},
        )
        hours = {row.segment_id: row.hours for row in result.allocations}
        self.assertEqual(hours["URGENT"], 6)
        self.assertEqual(hours["NORMAL"], 2)

    def test_resources_have_independent_capacity(self) -> None:
        result = build_allocation_plan(
            [
                SegmentInput("S1", "LABOR-A", D1, D1, 8, "Flexible"),
                SegmentInput("S2", "EQUIPMENT-A", D1, D1, 8, "Flexible"),
            ],
            [],
            {("LABOR-A", D1): 8, ("EQUIPMENT-A", D1): 8},
        )
        self.assertEqual(result.allocated_hours, 16)
        self.assertEqual(result.unallocated_hours, 0)

    def test_locked_allocation_for_unknown_segment_is_ignored(self) -> None:
        result = build_allocation_plan(
            [SegmentInput("S1", "R1", D1, D1, 8, "Flexible")],
            [LockedAllocationInput("OLD", "R1", D1, 4)],
            {("R1", D1): 8},
        )
        self.assertEqual(result.locked_allocation_count, 0)
        self.assertEqual(result.allocated_hours, 8)

    def test_multi_day_flexible_work_spreads_across_window(self) -> None:
        result = build_allocation_plan(
            [SegmentInput("S1", "R1", D1, D2, 8, "Flexible")],
            [],
            {("R1", D1): 8, ("R1", D2): 8},
        )
        by_day = {row.day: row.hours for row in result.allocations}
        self.assertEqual(by_day, {D1: 4, D2: 4})

    def test_invalid_window_remains_unallocated(self) -> None:
        result = build_allocation_plan(
            [SegmentInput("S1", "R1", D2, D1, 8, "Flexible")],
            [],
            {("R1", D1): 8, ("R1", D2): 8},
        )
        self.assertEqual(result.allocations, ())
        self.assertEqual(result.unallocated_hours, 8)


if __name__ == "__main__":
    unittest.main()
