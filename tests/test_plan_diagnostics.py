from __future__ import annotations

import unittest
from datetime import date

from app.domain.plan_diagnostics import summarize_segment_allocation_bounds
from app.domain.planning_engine import PlannedAllocation, SegmentInput


DAY = date(2026, 8, 18)


class PlanDiagnosticsTests(unittest.TestCase):
    def segment(self, ident: str = "S1", hours: float = 8) -> SegmentInput:
        return SegmentInput(ident, "R1", DAY, DAY, hours)

    def allocation(
        self,
        hours: float,
        *,
        ident: str = "S1",
        locked: bool = False,
        counts_as_allocated: bool = True,
    ) -> PlannedAllocation:
        return PlannedAllocation(
            segment_id=ident,
            resource_id="R1",
            day=DAY,
            hours=hours,
            allocation_type="Locked" if locked else "Flexible",
            locked=locked,
            counts_as_allocated=counts_as_allocated,
        )

    def test_normal_plan_has_no_overallocation(self) -> None:
        summary = summarize_segment_allocation_bounds(
            [self.segment()],
            [self.allocation(8)],
        )
        self.assertEqual(summary.overallocated_segment_count, 0)
        self.assertEqual(summary.overallocated_hours, 0)
        self.assertEqual(summary.locked_overallocated_segment_count, 0)

    def test_locked_hours_above_segment_budget_are_reported(self) -> None:
        summary = summarize_segment_allocation_bounds(
            [self.segment(hours=8)],
            [self.allocation(12, locked=True)],
        )
        self.assertEqual(summary.overallocated_segment_count, 1)
        self.assertEqual(summary.overallocated_hours, 4)
        self.assertEqual(summary.locked_overallocated_segment_count, 1)
        self.assertEqual(summary.locked_excess_hours, 4)
        self.assertEqual(summary.max_segment_excess_hours, 4)

    def test_locked_hours_with_automatic_remainder_do_not_overallocate(self) -> None:
        summary = summarize_segment_allocation_bounds(
            [self.segment(hours=8)],
            [self.allocation(6, locked=True), self.allocation(2)],
        )
        self.assertEqual(summary.overallocated_segment_count, 0)
        self.assertEqual(summary.locked_overallocated_segment_count, 0)

    def test_non_counting_missing_placeholder_is_excluded(self) -> None:
        summary = summarize_segment_allocation_bounds(
            [self.segment(hours=8)],
            [
                self.allocation(8),
                self.allocation(4, counts_as_allocated=False),
            ],
        )
        self.assertEqual(summary.overallocated_segment_count, 0)
        self.assertEqual(summary.overallocated_hours, 0)

    def test_multiple_segment_excesses_are_aggregated_without_identifiers(self) -> None:
        summary = summarize_segment_allocation_bounds(
            [self.segment("S1", 8), self.segment("S2", 5)],
            [
                self.allocation(10, ident="S1", locked=True),
                self.allocation(8, ident="S2", locked=True),
            ],
        )
        self.assertEqual(summary.overallocated_segment_count, 2)
        self.assertEqual(summary.overallocated_hours, 5)
        self.assertEqual(summary.locked_overallocated_segment_count, 2)
        self.assertEqual(summary.locked_excess_hours, 5)
        self.assertEqual(summary.max_segment_excess_hours, 3)


if __name__ == "__main__":
    unittest.main()
