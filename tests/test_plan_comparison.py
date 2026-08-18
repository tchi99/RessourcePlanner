from __future__ import annotations

import unittest
from datetime import date

from app.domain.plan_comparison import AllocationProjection, compare_allocation_plans


DAY = date(2026, 8, 18)


class PlanComparisonTests(unittest.TestCase):
    def allocation(
        self,
        *,
        hours: float,
        segment: str = "SEG-1",
        resource: str = "RES-1",
        allocation_type: str = "Flexible",
        locked: bool = False,
        outside_schedule: bool = False,
    ) -> AllocationProjection:
        return AllocationProjection(
            segment_id=segment,
            resource_id=resource,
            day=DAY,
            hours=hours,
            allocation_type=allocation_type,
            locked=locked,
            outside_schedule=outside_schedule,
        )

    def test_identical_plans_match(self) -> None:
        comparison = compare_allocation_plans(
            [self.allocation(hours=4)],
            [self.allocation(hours=4)],
        )
        self.assertTrue(comparison.matches)
        self.assertEqual(comparison.differences, ())

    def test_generated_row_splits_are_aggregated(self) -> None:
        comparison = compare_allocation_plans(
            [self.allocation(hours=2), self.allocation(hours=2)],
            [self.allocation(hours=4)],
        )
        self.assertTrue(comparison.matches)
        self.assertEqual(comparison.compared_keys, 1)

    def test_comparison_uses_excel_two_decimal_precision(self) -> None:
        comparison = compare_allocation_plans(
            [self.allocation(hours=2.3333)],
            [self.allocation(hours=2.3349)],
        )
        self.assertTrue(comparison.matches)

    def test_hour_difference_is_reported(self) -> None:
        comparison = compare_allocation_plans(
            [self.allocation(hours=4)],
            [self.allocation(hours=3.5)],
        )
        self.assertFalse(comparison.matches)
        self.assertEqual(len(comparison.differences), 1)
        self.assertEqual(comparison.differences[0].legacy_hours, 4)
        self.assertEqual(comparison.differences[0].shadow_hours, 3.5)

    def test_locked_type_is_normalized(self) -> None:
        comparison = compare_allocation_plans(
            [self.allocation(hours=2, allocation_type="Fixe", locked=True)],
            [self.allocation(hours=2, allocation_type="Locked", locked=True)],
        )
        self.assertTrue(comparison.matches)

    def test_resource_and_outside_schedule_are_semantic_keys(self) -> None:
        resource_diff = compare_allocation_plans(
            [self.allocation(hours=2, resource="RES-1")],
            [self.allocation(hours=2, resource="RES-2")],
        )
        outside_diff = compare_allocation_plans(
            [self.allocation(hours=2, locked=True, outside_schedule=False)],
            [self.allocation(hours=2, locked=True, outside_schedule=True)],
        )
        self.assertFalse(resource_diff.matches)
        self.assertFalse(outside_diff.matches)


if __name__ == "__main__":
    unittest.main()
