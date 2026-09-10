from __future__ import annotations

from datetime import date
import unittest

from app.domain.capacity_projection import projected_hours_in_window


class CapacityProjectionTests(unittest.TestCase):
    def test_full_range_projects_all_hours(self) -> None:
        self.assertEqual(
            projected_hours_in_window(
                40,
                date(2026, 9, 7),
                date(2026, 9, 11),
                date(2026, 9, 7),
                date(2026, 9, 13),
            ),
            40.0,
        )

    def test_projection_is_prorated_on_business_days_only(self) -> None:
        self.assertEqual(
            projected_hours_in_window(
                80,
                date(2026, 9, 7),
                date(2026, 9, 18),
                date(2026, 9, 7),
                date(2026, 9, 13),
            ),
            40.0,
        )

    def test_weekend_inside_window_does_not_absorb_macro_hours(self) -> None:
        self.assertEqual(
            projected_hours_in_window(
                40,
                date(2026, 9, 7),
                date(2026, 9, 13),
                date(2026, 9, 12),
                date(2026, 9, 13),
            ),
            0.0,
        )

    def test_outside_window_returns_zero(self) -> None:
        self.assertEqual(
            projected_hours_in_window(
                40,
                date(2026, 9, 7),
                date(2026, 9, 11),
                date(2026, 9, 14),
                date(2026, 9, 20),
            ),
            0.0,
        )

    def test_reversed_range_and_window_are_normalized(self) -> None:
        self.assertEqual(
            projected_hours_in_window(
                40,
                date(2026, 9, 11),
                date(2026, 9, 7),
                date(2026, 9, 13),
                date(2026, 9, 7),
            ),
            40.0,
        )

    def test_negative_or_missing_inputs_never_create_load(self) -> None:
        self.assertEqual(
            projected_hours_in_window(
                -8,
                date(2026, 9, 7),
                date(2026, 9, 11),
                date(2026, 9, 7),
                date(2026, 9, 13),
            ),
            0.0,
        )
        self.assertEqual(
            projected_hours_in_window(
                8,
                None,
                None,
                date(2026, 9, 7),
                date(2026, 9, 13),
            ),
            0.0,
        )


if __name__ == "__main__":
    unittest.main()
