from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import date, timedelta
from typing import Any

from app.domain.planning_engine import (
    LockedAllocationInput,
    SegmentInput,
    build_allocation_plan,
)


BASE_DAY = date(2026, 1, 5)
DEFAULT_SIZES = (50, 250, 1000)


def build_fixture(
    segment_count: int,
) -> tuple[
    list[SegmentInput],
    list[LockedAllocationInput],
    dict[tuple[str, date], float],
    dict[tuple[str, date], bool],
]:
    """Build deterministic synthetic planning data with no business identifiers."""
    count = max(int(segment_count), 1)
    resource_count = max(1, min(40, (count + 9) // 10))
    resources = [f"R{index:02d}" for index in range(resource_count)]

    capacity: dict[tuple[str, date], float] = {}
    outside_eligible: dict[tuple[str, date], bool] = {}
    for resource in resources:
        for offset in range(70):
            day = BASE_DAY + timedelta(days=offset)
            capacity[(resource, day)] = 8.0 if day.weekday() < 5 else 0.0
            outside_eligible[(resource, day)] = True

    segments: list[SegmentInput] = []
    locked: list[LockedAllocationInput] = []
    for index in range(count):
        resource = resources[index % resource_count]
        start = BASE_DAY + timedelta(days=(index // resource_count) % 45)
        end = start + timedelta(days=4 + (index % 3))
        hours = float((index % 4 + 1) * 8)
        segment = SegmentInput(
            segment_id=f"S{index:05d}",
            resource_id=resource,
            start=start,
            end=end,
            hours=hours,
            plan_type="Fixe" if index % 5 == 0 else "Flexible",
            priority_rank=index % 4,
            created_order=f"{index:08d}",
            overtime_allowed=index % 13 == 0,
        )
        segments.append(segment)
        if index % 11 == 0:
            locked.append(
                LockedAllocationInput(
                    segment_id=segment.segment_id,
                    resource_id=resource,
                    day=start,
                    hours=2.0,
                )
            )

    return segments, locked, capacity, outside_eligible


def benchmark_case(segment_count: int, iterations: int = 5) -> dict[str, Any]:
    segments, locked, capacity, outside_eligible = build_fixture(segment_count)

    # Warm-up avoids measuring module/runtime initialization noise.
    build_allocation_plan(
        segments,
        locked,
        capacity,
        outside_schedule_eligible_by_resource_day=outside_eligible,
    )

    samples: list[float] = []
    allocation_count = 0
    for _ in range(max(iterations, 1)):
        started = time.perf_counter()
        result = build_allocation_plan(
            segments,
            locked,
            capacity,
            outside_schedule_eligible_by_resource_day=outside_eligible,
        )
        samples.append(time.perf_counter() - started)
        allocation_count = len(result.allocations)

    ordered = sorted(samples)
    p95_index = min(len(ordered) - 1, max(0, int(round(0.95 * len(ordered) + 0.5)) - 1))
    return {
        "segments": len(segments),
        "locked_allocations": len(locked),
        "result_allocations": allocation_count,
        "iterations": len(samples),
        "median_seconds": round(statistics.median(samples), 6),
        "min_seconds": round(min(samples), 6),
        "max_seconds": round(max(samples), 6),
        "p95_seconds": round(ordered[p95_index], 6),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark reproductible du moteur pur RessourcePlanner.")
    parser.add_argument(
        "--sizes",
        type=int,
        nargs="+",
        default=list(DEFAULT_SIZES),
        help="Tailles synthétiques à mesurer (défaut: 50 250 1000).",
    )
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--json", action="store_true", help="Produit du JSON plutôt qu'un tableau texte.")
    args = parser.parse_args()

    results = [benchmark_case(size, args.iterations) for size in args.sizes if size > 0]
    if args.json:
        print(json.dumps(results, indent=2, sort_keys=True))
        return 0

    print("segments | locked | allocations | iterations | median | p95 | max")
    for row in results:
        print(
            f"{row['segments']:8d} | {row['locked_allocations']:6d} | "
            f"{row['result_allocations']:11d} | {row['iterations']:10d} | "
            f"{row['median_seconds']:.6f}s | {row['p95_seconds']:.6f}s | "
            f"{row['max_seconds']:.6f}s"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
