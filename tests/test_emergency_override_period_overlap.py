from __future__ import annotations

from datetime import date
import unittest

from app.application import DemandPeriodReadModel, DemandReadModel, emergency_override_eligibility


class EmergencyOverridePeriodOverlapTests(unittest.TestCase):
    def test_disjoint_effective_periods_do_not_create_artificial_week_overlap(self) -> None:
        today = date(2026, 9, 16)
        demand = DemandReadModel(
            number="D-GAP",
            status="Soumise",
            priority="Urgent",
            desired_start=date(2026, 9, 1),
            desired_end=date(2026, 10, 1),
        )
        periods = (
            DemandPeriodReadModel(
                period_id="P1",
                demand_number="D-GAP",
                sequence=1,
                kind="CUMULATIVE",
                start_date=date(2026, 9, 1),
                end_date=date(2026, 9, 1),
                hours=8,
                confirmation="Confirmée",
            ),
            DemandPeriodReadModel(
                period_id="P2",
                demand_number="D-GAP",
                sequence=2,
                kind="CUMULATIVE",
                start_date=date(2026, 10, 1),
                end_date=date(2026, 10, 1),
                hours=8,
                confirmation="Confirmée",
            ),
        )

        self.assertEqual(
            emergency_override_eligibility(demand, today=today, periods=periods),
            (False, "OUTSIDE_CURRENT_WEEK"),
        )


if __name__ == "__main__":
    unittest.main()
