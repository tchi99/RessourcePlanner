from __future__ import annotations

from datetime import date
import unittest

from app.domain.demand_periods import (
    PERIOD_KIND_ALTERNATIVE,
    PERIOD_KIND_CUMULATIVE,
    DemandPeriodDefinition,
    effective_period_ids,
    projected_hours_without_double_counting,
    validate_period_definitions,
)


DAY_1 = date(2026, 9, 7)
DAY_2 = date(2026, 9, 8)


class DemandPeriodPolicyTests(unittest.TestCase):
    def alternatives(self) -> tuple[DemandPeriodDefinition, DemandPeriodDefinition]:
        return (
            DemandPeriodDefinition(
                period_id="OPT-A",
                start_date=DAY_1,
                end_date=DAY_1,
                hours=8,
                kind=PERIOD_KIND_ALTERNATIVE,
                alternative_group="TECH-DAY",
                proposed_resource="Technicien A",
            ),
            DemandPeriodDefinition(
                period_id="OPT-B",
                start_date=DAY_2,
                end_date=DAY_2,
                hours=8,
                kind=PERIOD_KIND_ALTERNATIVE,
                alternative_group="TECH-DAY",
                proposed_resource="Technicien B",
            ),
        )

    def test_unresolved_alternative_group_materializes_neither_option(self) -> None:
        periods = self.alternatives()
        self.assertEqual(effective_period_ids(periods, {}), ())

    def test_selecting_one_alternative_never_materializes_the_other(self) -> None:
        periods = self.alternatives()
        self.assertEqual(
            effective_period_ids(periods, {"TECH-DAY": "OPT-A"}),
            ("OPT-A",),
        )
        self.assertEqual(
            effective_period_ids(periods, {"TECH-DAY": "OPT-B"}),
            ("OPT-B",),
        )

    def test_unresolved_group_projects_once_instead_of_summing_both_options(self) -> None:
        periods = (
            self.alternatives()[0],
            DemandPeriodDefinition(
                period_id="OPT-B",
                start_date=DAY_2,
                end_date=DAY_2,
                hours=6,
                kind=PERIOD_KIND_ALTERNATIVE,
                alternative_group="TECH-DAY",
                proposed_resource="Technicien B",
            ),
        )
        self.assertEqual(projected_hours_without_double_counting(periods), 8.0)
        self.assertEqual(
            projected_hours_without_double_counting(
                periods, {"TECH-DAY": "OPT-B"}
            ),
            6.0,
        )

    def test_cumulative_periods_add_to_one_projected_alternative(self) -> None:
        periods = (
            DemandPeriodDefinition(
                period_id="FIXED",
                start_date=DAY_1,
                end_date=DAY_1,
                hours=4,
                kind=PERIOD_KIND_CUMULATIVE,
            ),
            *self.alternatives(),
        )
        self.assertEqual(projected_hours_without_double_counting(periods), 12.0)
        self.assertEqual(
            effective_period_ids(periods, {"TECH-DAY": "OPT-A"}),
            ("FIXED", "OPT-A"),
        )

    def test_singleton_alternative_group_is_invalid(self) -> None:
        with self.assertRaisesRegex(ValueError, "au moins deux options"):
            validate_period_definitions((self.alternatives()[0],))

    def test_selection_must_belong_to_requested_group(self) -> None:
        periods = self.alternatives()
        with self.assertRaisesRegex(ValueError, "n'appartient pas"):
            effective_period_ids(periods, {"AUTRE-GROUPE": "OPT-A"})


if __name__ == "__main__":
    unittest.main()
