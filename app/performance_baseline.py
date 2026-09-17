from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Iterable, Mapping, Sequence


DATASET_ORDER = ("small", "medium", "large")


@dataclass(frozen=True, slots=True)
class EndpointBudget:
    """Wide CI guardrails for a representative V2 API endpoint.

    Query-count invariants are intentionally stronger than wall-clock limits. Timing
    on GitHub-hosted SQLite runners is useful as a baseline, not as a production SLA.
    """

    max_queries: int
    max_selects: int
    max_repeated_query: int
    max_query_growth: int
    coarse_p99_seconds: float
    allow_n_plus_one: bool = False


DEFAULT_ENDPOINT_BUDGETS: dict[str, EndpointBudget] = {
    "http GET /api/v1/projects": EndpointBudget(2, 2, 1, 1, 5.0),
    "http GET /api/v1/resources": EndpointBudget(2, 2, 1, 1, 5.0),
    "http GET /api/v1/demands": EndpointBudget(2, 2, 1, 1, 5.0),
    "http GET /api/v1/segments": EndpointBudget(2, 2, 1, 1, 5.0),
    "http GET /api/v1/shifts": EndpointBudget(2, 2, 1, 1, 5.0),
    # list_pending_loads currently reads submitted requests individually. #252 makes
    # that scaling debt visible without pretending it has already been optimized.
    "http GET /api/v1/planning/snapshot": EndpointBudget(
        max_queries=180,
        max_selects=180,
        max_repeated_query=64,
        max_query_growth=160,
        coarse_p99_seconds=15.0,
        allow_n_plus_one=True,
    ),
}


@dataclass(frozen=True, slots=True)
class BudgetViolation:
    dataset: str
    operation: str
    metric: str
    actual: float | int | bool
    limit: float | int | bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def percentile(values: Iterable[object], quantile: float) -> float:
    numeric = sorted(max(float(value or 0.0), 0.0) for value in values)
    if not numeric:
        return 0.0
    if len(numeric) == 1:
        return round(numeric[0], 6)
    rank = (len(numeric) - 1) * min(max(float(quantile), 0.0), 1.0)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return round(numeric[lower], 6)
    weight = rank - lower
    return round(numeric[lower] * (1.0 - weight) + numeric[upper] * weight, 6)


def aggregate_operation(samples: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate instrumentation samples without carrying business identifiers."""

    if not samples:
        return {}
    operation = str(samples[0].get("operation") or "")
    phases = (
        "auth_seconds",
        "api_seconds",
        "db_seconds",
        "compute_seconds",
        "serialization_seconds",
        "external_seconds",
    )
    result: dict[str, Any] = {
        "operation": operation,
        "sample_count": len(samples),
        "total_seconds": {
            "p50": percentile((row.get("total_seconds", 0.0) for row in samples), 0.50),
            "p95": percentile((row.get("total_seconds", 0.0) for row in samples), 0.95),
            "p99": percentile((row.get("total_seconds", 0.0) for row in samples), 0.99),
        },
        "db_query_count": {
            "p50": percentile((row.get("db_query_count", 0) for row in samples), 0.50),
            "p95": percentile((row.get("db_query_count", 0) for row in samples), 0.95),
            "max": max(int(row.get("db_query_count") or 0) for row in samples),
        },
        "db_select_count": {
            "p95": percentile((row.get("db_select_count", 0) for row in samples), 0.95),
            "max": max(int(row.get("db_select_count") or 0) for row in samples),
        },
        "db_repeated_query_max": max(
            int(row.get("db_repeated_query_max") or 0) for row in samples
        ),
        "db_n_plus_one_suspected": any(
            bool(row.get("db_n_plus_one_suspected")) for row in samples
        ),
        "db_slow_query_count_max": max(
            int(row.get("db_slow_query_count") or 0) for row in samples
        ),
        "external_call_count_max": max(
            int(row.get("external_call_count") or 0) for row in samples
        ),
    }
    result["phase_p95_seconds"] = {
        phase.removesuffix("_seconds"): percentile(
            (row.get(phase, 0.0) for row in samples), 0.95
        )
        for phase in phases
    }
    return result


def aggregate_dataset(
    samples: Sequence[Mapping[str, Any]],
    *,
    dataset: str,
    shape: Mapping[str, int],
) -> dict[str, Any]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in samples:
        operation = str(row.get("operation") or "")
        if operation.startswith("http "):
            grouped.setdefault(operation, []).append(row)
    return {
        "dataset": dataset,
        "shape": {str(key): int(value) for key, value in shape.items()},
        "operations": {
            operation: aggregate_operation(rows)
            for operation, rows in sorted(grouped.items())
        },
    }


def query_growth(
    reports: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    """Return max-query growth from smallest to largest available dataset."""

    by_name = {str(report.get("dataset") or ""): report for report in reports}
    ordered = [by_name[name] for name in DATASET_ORDER if name in by_name]
    if len(ordered) < 2:
        return {}
    first = ordered[0].get("operations", {})
    last = ordered[-1].get("operations", {})
    operations = set(first) & set(last)
    return {
        operation: int(last[operation]["db_query_count"]["max"])
        - int(first[operation]["db_query_count"]["max"])
        for operation in sorted(operations)
    }


def evaluate_budgets(
    reports: Sequence[Mapping[str, Any]],
    *,
    budgets: Mapping[str, EndpointBudget] | None = None,
) -> list[BudgetViolation]:
    """Evaluate broad structural budgets and coarse catastrophic-time guards."""

    active_budgets = dict(budgets or DEFAULT_ENDPOINT_BUDGETS)
    growth = query_growth(reports)
    violations: list[BudgetViolation] = []
    for report in reports:
        dataset = str(report.get("dataset") or "unknown")
        operations = report.get("operations", {})
        for operation, budget in active_budgets.items():
            metrics = operations.get(operation)
            if not metrics:
                violations.append(
                    BudgetViolation(dataset, operation, "missing_operation", True, False)
                )
                continue
            checks = (
                ("db_query_count", int(metrics["db_query_count"]["max"]), budget.max_queries),
                ("db_select_count", int(metrics["db_select_count"]["max"]), budget.max_selects),
                (
                    "db_repeated_query_max",
                    int(metrics["db_repeated_query_max"]),
                    budget.max_repeated_query,
                ),
                (
                    "total_p99_seconds",
                    float(metrics["total_seconds"]["p99"]),
                    budget.coarse_p99_seconds,
                ),
            )
            for metric, actual, limit in checks:
                if actual > limit:
                    violations.append(
                        BudgetViolation(dataset, operation, metric, actual, limit)
                    )
            if metrics["db_n_plus_one_suspected"] and not budget.allow_n_plus_one:
                violations.append(
                    BudgetViolation(dataset, operation, "db_n_plus_one_suspected", True, False)
                )

    if reports:
        largest = next(
            (
                name
                for name in reversed(DATASET_ORDER)
                if any(str(row.get("dataset")) == name for row in reports)
            ),
            str(reports[-1].get("dataset") or "unknown"),
        )
        for operation, actual_growth in growth.items():
            budget = active_budgets.get(operation)
            if budget is not None and actual_growth > budget.max_query_growth:
                violations.append(
                    BudgetViolation(
                        largest,
                        operation,
                        "db_query_growth",
                        actual_growth,
                        budget.max_query_growth,
                    )
                )
    return violations


def baseline_payload(
    reports: Sequence[Mapping[str, Any]],
    *,
    budgets: Mapping[str, EndpointBudget] | None = None,
) -> dict[str, Any]:
    active_budgets = dict(budgets or DEFAULT_ENDPOINT_BUDGETS)
    violations = evaluate_budgets(reports, budgets=active_budgets)
    return {
        "schema_version": 1,
        "environment": "sqlite-local-baseline",
        "production_interpretation": (
            "SQLite timings are a reproducible local/CI baseline only; they are not "
            "SQL Server production latency targets."
        ),
        "datasets": list(reports),
        "query_growth": query_growth(reports),
        "budgets": {
            operation: asdict(budget) for operation, budget in sorted(active_budgets.items())
        },
        "violations": [violation.to_dict() for violation in violations],
        "passed": not violations,
    }


def format_baseline_report(payload: Mapping[str, Any]) -> str:
    lines = [
        "V2 API performance baseline — SQLite",
        "NOTE: SQLite timings are comparative local/CI evidence, not SQL Server production SLAs.",
        "",
        "dataset | operation | n | p50 | p95 | p99 | queries max | selects max | repeated max | n+1",
    ]
    for dataset in payload.get("datasets", ()):  # type: ignore[assignment]
        name = str(dataset.get("dataset") or "")
        for operation, metrics in dataset.get("operations", {}).items():
            total = metrics["total_seconds"]
            lines.append(
                f"{name} | {operation} | {metrics['sample_count']} | "
                f"{total['p50']:.4f}s | {total['p95']:.4f}s | {total['p99']:.4f}s | "
                f"{metrics['db_query_count']['max']} | {metrics['db_select_count']['max']} | "
                f"{metrics['db_repeated_query_max']} | {metrics['db_n_plus_one_suspected']}"
            )
    lines.extend(("", "query growth (small → large):"))
    for operation, growth in payload.get("query_growth", {}).items():
        lines.append(f"- {operation}: {growth:+d} query(s)")
    violations = payload.get("violations", ())
    if violations:
        lines.extend(("", "BUDGET: FAIL"))
        for row in violations:
            lines.append(
                f"- {row['dataset']} {row['operation']} {row['metric']}: "
                f"{row['actual']} > {row['limit']}"
            )
    else:
        lines.extend(("", "BUDGET: PASS"))
    return "\n".join(lines)
