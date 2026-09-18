from __future__ import annotations

import unittest

from app.performance_baseline import (
    EndpointBudget,
    aggregate_dataset,
    baseline_payload,
    compare_baselines,
    evaluate_budgets,
    percentile,
    query_growth,
)


OPERATION = "http GET /api/v1/example"


def _sample(*, total: float, queries: int, repeated: int = 1, n_plus_one: bool = False):
    return {
        "operation": OPERATION,
        "total_seconds": total,
        "auth_seconds": 0.001,
        "api_seconds": 0.002,
        "db_seconds": 0.003,
        "compute_seconds": 0.004,
        "serialization_seconds": 0.005,
        "external_seconds": 0.0,
        "db_query_count": queries,
        "db_select_count": queries,
        "db_repeated_query_max": repeated,
        "db_n_plus_one_suspected": n_plus_one,
        "db_slow_query_count": 0,
        "external_call_count": 0,
    }


def _report(dataset: str, queries: int, *, n_plus_one: bool = False):
    return aggregate_dataset(
        [_sample(total=value, queries=queries, repeated=(5 if n_plus_one else 1), n_plus_one=n_plus_one)
         for value in (0.10, 0.20, 0.30)],
        dataset=dataset,
        shape={"demands": {"small": 10, "medium": 50, "large": 100}[dataset]},
    )


class V2PerformanceBaselineTests(unittest.TestCase):
    def test_percentile_interpolates_p50_p95_and_p99(self) -> None:
        values = (1.0, 2.0, 3.0)
        self.assertEqual(percentile(values, 0.50), 2.0)
        self.assertEqual(percentile(values, 0.95), 2.9)
        self.assertEqual(percentile(values, 0.99), 2.98)

    def test_dataset_aggregation_keeps_only_technical_metrics(self) -> None:
        report = aggregate_dataset(
            [_sample(total=0.1, queries=2), _sample(total=0.2, queries=3)],
            dataset="small",
            shape={"projects": 8, "resources": 16},
        )

        metrics = report["operations"][OPERATION]
        self.assertEqual(metrics["sample_count"], 2)
        self.assertEqual(metrics["db_query_count"]["max"], 3)
        self.assertEqual(metrics["db_select_count"]["max"], 3)
        self.assertEqual(metrics["phase_p95_seconds"]["db"], 0.003)
        self.assertNotIn("path", str(report).casefold())
        self.assertNotIn("project_number", str(report).casefold())

    def test_query_growth_compares_smallest_and_largest_dataset(self) -> None:
        reports = [_report("small", 2), _report("medium", 4), _report("large", 7)]
        self.assertEqual(query_growth(reports)[OPERATION], 5)

    def test_budget_rejects_new_n_plus_one_and_query_growth(self) -> None:
        reports = [_report("small", 2), _report("medium", 5), _report("large", 12, n_plus_one=True)]
        budget = EndpointBudget(
            max_queries=20,
            max_selects=20,
            max_repeated_query=10,
            max_query_growth=5,
            coarse_p99_seconds=5.0,
            allow_n_plus_one=False,
        )

        violations = evaluate_budgets(reports, budgets={OPERATION: budget})
        metrics = {row.metric for row in violations}
        self.assertIn("db_n_plus_one_suspected", metrics)
        self.assertIn("db_query_growth", metrics)

    def test_known_scaling_debt_can_be_visible_without_failing_budget(self) -> None:
        reports = [_report("small", 8, n_plus_one=True), _report("large", 20, n_plus_one=True)]
        budget = EndpointBudget(
            max_queries=30,
            max_selects=30,
            max_repeated_query=10,
            max_query_growth=20,
            coarse_p99_seconds=5.0,
            allow_n_plus_one=True,
        )

        self.assertEqual(evaluate_budgets(reports, budgets={OPERATION: budget}), [])
        payload = baseline_payload(reports, budgets={OPERATION: budget})
        self.assertTrue(payload["passed"])
        self.assertIn("not SQL Server production latency targets", payload["production_interpretation"])

    def test_before_after_comparison_reports_latency_and_query_deltas(self) -> None:
        before = baseline_payload([_report("small", 2), _report("large", 4)])
        after = baseline_payload([_report("small", 3), _report("large", 7)])
        comparison = compare_baselines(before, after)

        small = comparison["datasets"]["small"]["operations"][OPERATION]
        large = comparison["datasets"]["large"]["operations"][OPERATION]
        self.assertEqual(small["db_queries_delta"], 1)
        self.assertEqual(large["db_queries_delta"], 3)
        self.assertEqual(small["p95_seconds_delta"], 0.0)

    def test_missing_representative_operation_fails_closed(self) -> None:
        budget = EndpointBudget(2, 2, 1, 1, 5.0)
        violations = evaluate_budgets(
            [{"dataset": "small", "shape": {}, "operations": {}}],
            budgets={OPERATION: budget},
        )
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].metric, "missing_operation")


if __name__ == "__main__":
    unittest.main()
