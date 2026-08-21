from __future__ import annotations

import unittest

from tools.benchmark_planning_engine import benchmark_case, build_fixture


class PlanningEngineBenchmarkTests(unittest.TestCase):
    def test_fixture_is_deterministic_and_synthetic(self) -> None:
        first = build_fixture(50)
        second = build_fixture(50)
        self.assertEqual(first, second)
        self.assertTrue(all(segment.segment_id.startswith("S") for segment in first[0]))
        self.assertTrue(all(segment.resource_id.startswith("R") for segment in first[0]))

    def test_250_segment_case_stays_below_coarse_regression_guard(self) -> None:
        """Catch catastrophic slowdowns; tighten after collecting real CI baselines."""
        result = benchmark_case(250, iterations=2)
        self.assertLess(
            result["max_seconds"],
            3.0,
            f"Pure engine benchmark regressed: {result}",
        )


if __name__ == "__main__":
    unittest.main()
