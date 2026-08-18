from __future__ import annotations

import unittest
from datetime import date

from app.domain.calendar_rules import (
    business_days,
    effort_overlaps_day,
    week_days,
    week_start,
)


class CalendarRulesTests(unittest.TestCase):
    def test_week_start_returns_monday(self) -> None:
        self.assertEqual(week_start(date(2026, 8, 18)), date(2026, 8, 17))
        self.assertEqual(week_start(date(2026, 8, 17)), date(2026, 8, 17))

    def test_week_days_returns_seven_consecutive_days(self) -> None:
        start = date(2026, 8, 17)
        days = week_days(start)
        self.assertEqual(len(days), 7)
        self.assertEqual(days[0], start)
        self.assertEqual(days[-1], date(2026, 8, 23))

    def test_business_days_counts_weekdays_inclusively(self) -> None:
        self.assertEqual(business_days(date(2026, 8, 17), date(2026, 8, 21)), 5)
        self.assertEqual(business_days(date(2026, 8, 21), date(2026, 8, 24)), 2)

    def test_business_days_accepts_reversed_range(self) -> None:
        self.assertEqual(business_days(date(2026, 8, 21), date(2026, 8, 17)), 5)

    def test_business_days_preserves_historical_minimum_of_one(self) -> None:
        self.assertEqual(business_days(date(2026, 8, 22), date(2026, 8, 23)), 1)

    def test_effort_overlap_is_inclusive(self) -> None:
        effort = {
            "Date de début": date(2026, 8, 18),
            "Date de fin": date(2026, 8, 20),
        }
        self.assertTrue(effort_overlaps_day(effort, date(2026, 8, 18)))
        self.assertTrue(effort_overlaps_day(effort, date(2026, 8, 20)))
        self.assertFalse(effort_overlaps_day(effort, date(2026, 8, 21)))

    def test_effort_without_end_date_is_single_day(self) -> None:
        effort = {"Date de début": date(2026, 8, 18), "Date de fin": None}
        self.assertTrue(effort_overlaps_day(effort, date(2026, 8, 18)))
        self.assertFalse(effort_overlaps_day(effort, date(2026, 8, 19)))

    def test_effort_without_start_does_not_overlap(self) -> None:
        self.assertFalse(effort_overlaps_day({}, date(2026, 8, 18)))


if __name__ == "__main__":
    unittest.main()
