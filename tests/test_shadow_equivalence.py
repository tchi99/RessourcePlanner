from __future__ import annotations

import unittest
from datetime import date

from app.domain.plan_comparison import AllocationProjection, compare_allocation_plans
from app.domain.planning_engine import (
    MISSING_ALLOCATION_TYPE,
    LockedAllocationInput,
    SegmentInput,
    build_allocation_plan,
)


D1 = date(2026, 8, 17)
D2 = date(2026, 8, 18)


def project_shadow(result) -> list[AllocationProjection]:
    return [
        AllocationProjection(
            segment_id=row.segment_id,
            resource_id=row.resource_id,
            day=row.day,
            hours=row.hours,
            allocation_type=row.allocation_type,
            locked=row.locked,
            outside_schedule=row.outside_schedule,
        )
        for row in result.allocations
    ]


class ShadowEquivalenceTests(unittest.TestCase):
    def test_locked_fixed_and_flexible_fixture_matches_refined_persistence(self) -> None:
        shadow = build_allocation_plan(
            [
                SegmentInput("FIX", "R1", D1, D2, 12, "Fixe"),
                SegmentInput("FLEX", "R1", D1, D2, 8, "Flexible"),
            ],
            [LockedAllocationInput("FIX", "R1", D1, 2)],
            {("R1", D1): 8, ("R1", D2): 8},
        )

        legacy = [
            AllocationProjection("FIX", "R1", D1, 2.00, "Fixe", locked=True),
            AllocationProjection("FIX", "R1", D1, 4.29, "Fixe"),
            AllocationProjection("FIX", "R1", D2, 5.71, "Fixe"),
            AllocationProjection("FLEX", "R1", D1, 1.71, "Flexible"),
            AllocationProjection("FLEX", "R1", D2, 2.29, "Flexible"),
            AllocationProjection("FLEX", "R1", D1, 4.00, MISSING_ALLOCATION_TYPE),
        ]
        comparison = compare_allocation_plans(legacy, project_shadow(shadow))
        self.assertTrue(comparison.matches, comparison.differences)
        self.assertEqual(shadow.unallocated_hours, 4)
        self.assertEqual(shadow.missing_allocation_count, 1)

    def test_fixed_shortage_fixture_matches_refined_persistence(self) -> None:
        shadow = build_allocation_plan(
            [SegmentInput("FIX", "R1", D1, D1, 12, "Fixe")],
            [],
            {("R1", D1): 8},
        )
        legacy = [
            AllocationProjection("FIX", "R1", D1, 8.00, "Fixe"),
            AllocationProjection("FIX", "R1", D1, 4.00, MISSING_ALLOCATION_TYPE),
        ]
        comparison = compare_allocation_plans(legacy, project_shadow(shadow))
        self.assertTrue(comparison.matches, comparison.differences)
        self.assertEqual(shadow.allocated_hours, 8)
        self.assertEqual(shadow.unallocated_hours, 4)

    def test_flexible_shortage_fixture_matches_refined_persistence(self) -> None:
        shadow = build_allocation_plan(
            [SegmentInput("FLEX", "R1", D1, D1, 12, "Flexible")],
            [],
            {("R1", D1): 8},
        )
        legacy = [
            AllocationProjection("FLEX", "R1", D1, 8.00, "Flexible"),
            AllocationProjection("FLEX", "R1", D1, 4.00, MISSING_ALLOCATION_TYPE),
        ]
        comparison = compare_allocation_plans(legacy, project_shadow(shadow))
        self.assertTrue(comparison.matches, comparison.differences)
        self.assertEqual(shadow.allocated_hours, 8)
        self.assertEqual(shadow.unallocated_hours, 4)

    def test_authorized_flexible_overtime_fixture_matches_refined_persistence(self) -> None:
        shadow = build_allocation_plan(
            [SegmentInput("FLEX", "R1", D1, D1, 12, "Flexible", overtime_allowed=True)],
            [],
            {("R1", D1): 8},
        )
        legacy = [
            AllocationProjection("FLEX", "R1", D1, 8.00, "Flexible"),
            AllocationProjection(
                "FLEX",
                "R1",
                D1,
                4.00,
                "Flexible",
                outside_schedule=True,
            ),
        ]
        comparison = compare_allocation_plans(legacy, project_shadow(shadow))
        self.assertTrue(comparison.matches, comparison.differences)
        self.assertEqual(shadow.allocated_hours, 12)
        self.assertEqual(shadow.overtime_hours, 4)
        self.assertEqual(shadow.unallocated_hours, 0)


if __name__ == "__main__":
    unittest.main()
