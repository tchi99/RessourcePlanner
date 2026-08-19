from __future__ import annotations

import unittest
from datetime import date

from app.domain.availability_rules import (
    availability_hours_for_day,
    has_standard_schedule,
    outside_schedule_eligible_for_day,
)


MONDAY = date(2026, 8, 17)
TUESDAY = date(2026, 8, 18)
SATURDAY = date(2026, 8, 22)


def standard(resource: str = "R1", start: object = "08:00", end: object = "16:00") -> dict[str, object]:
    return {
        "Technicien": resource,
        "Type": "Horaire standard",
        "JoursSemaine": "Lun,Mar,Mer,Jeu,Ven",
        "HeureDebut": start,
        "HeureFin": end,
        "Actif": "Oui",
    }


class AvailabilityRulesTests(unittest.TestCase):
    def test_resource_requires_explicit_standard_schedule(self) -> None:
        self.assertFalse(has_standard_schedule([], "R1"))
        self.assertEqual(availability_hours_for_day([], "R1", MONDAY), 0)
        self.assertFalse(outside_schedule_eligible_for_day([], "R1", MONDAY))

    def test_standard_schedule_returns_daily_hours(self) -> None:
        self.assertEqual(availability_hours_for_day([standard()], "R1", MONDAY), 8)
        self.assertEqual(availability_hours_for_day([standard()], "R1", SATURDAY), 0)

    def test_excel_fraction_times_are_supported(self) -> None:
        rows = [standard(start=8 / 24, end=16 / 24)]
        self.assertAlmostEqual(availability_hours_for_day(rows, "R1", MONDAY), 8, places=6)

    def test_excel_fraction_times_match_historical_minute_rounding(self) -> None:
        rows = [standard(start=0.333333, end=0.666667)]
        self.assertEqual(availability_hours_for_day(rows, "R1", MONDAY), 8)

    def test_overnight_schedule_wraps_to_next_day(self) -> None:
        rows = [standard(start="22:00", end="06:00")]
        self.assertEqual(availability_hours_for_day(rows, "R1", MONDAY), 8)

    def test_global_holiday_blocks_standard_capacity_but_allows_overtime_slot(self) -> None:
        rows = [
            standard(),
            {
                "Type": "Jour férié",
                "DateDebut": TUESDAY,
                "DateFin": TUESDAY,
                "Actif": "Oui",
            },
        ]
        self.assertEqual(availability_hours_for_day(rows, "R1", TUESDAY), 0)
        self.assertTrue(outside_schedule_eligible_for_day(rows, "R1", TUESDAY))

    def test_weekend_without_standard_capacity_allows_overtime_slot(self) -> None:
        rows = [standard()]
        self.assertEqual(availability_hours_for_day(rows, "R1", SATURDAY), 0)
        self.assertTrue(outside_schedule_eligible_for_day(rows, "R1", SATURDAY))

    def test_resource_specific_holiday_does_not_block_other_resource(self) -> None:
        rows = [
            standard("R1"),
            standard("R2"),
            {
                "Technicien": "R1",
                "Type": "Jour férié",
                "DateDebut": MONDAY,
                "DateFin": MONDAY,
                "Actif": "Oui",
            },
        ]
        self.assertEqual(availability_hours_for_day(rows, "R1", MONDAY), 0)
        self.assertEqual(availability_hours_for_day(rows, "R2", MONDAY), 8)

    def test_vacation_blocks_only_matching_resource_and_excludes_overtime_slot(self) -> None:
        rows = [
            standard("R1"),
            standard("R2"),
            {
                "Technicien": "R1",
                "Type": "Vacances",
                "DateDebut": MONDAY,
                "DateFin": TUESDAY,
                "Actif": "Oui",
            },
        ]
        self.assertEqual(availability_hours_for_day(rows, "R1", MONDAY), 0)
        self.assertEqual(availability_hours_for_day(rows, "R2", MONDAY), 8)
        self.assertFalse(outside_schedule_eligible_for_day(rows, "R1", MONDAY))
        self.assertTrue(outside_schedule_eligible_for_day(rows, "R2", MONDAY))

    def test_inactive_exception_is_ignored(self) -> None:
        rows = [
            standard(),
            {
                "Type": "Jour férié",
                "DateDebut": MONDAY,
                "DateFin": MONDAY,
                "Actif": "Non",
            },
        ]
        self.assertEqual(availability_hours_for_day(rows, "R1", MONDAY), 8)
        self.assertTrue(outside_schedule_eligible_for_day(rows, "R1", MONDAY))


if __name__ == "__main__":
    unittest.main()
