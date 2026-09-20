from __future__ import annotations

import argparse
import json
import sys
import time
import unittest
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass(frozen=True)
class TestTiming:
    seconds: float
    test_id: str
    module: str


def _iter_test_cases(suite: unittest.TestSuite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _iter_test_cases(item)
        else:
            yield item


def _load_module_weights(path: Path) -> dict[str, float]:
    if not path.exists():
        return {}

    raw = json.loads(path.read_text(encoding="utf-8"))
    modules = raw.get("modules", {})
    weights: dict[str, float] = {}
    for module, payload in modules.items():
        seconds = payload.get("seconds") if isinstance(payload, dict) else payload
        try:
            value = float(seconds)
        except (TypeError, ValueError):
            continue
        if value > 0:
            weights[str(module)] = value
    return weights


def _partition_by_module(
    cases: list[unittest.case.TestCase],
    shard_count: int,
    module_weights: dict[str, float] | None = None,
) -> tuple[list[list[unittest.case.TestCase]], list[float]]:
    """Distribute complete test modules across shards using historical duration weights."""

    modules: dict[str, list[unittest.case.TestCase]] = defaultdict(list)
    for case in cases:
        modules[case.__class__.__module__].append(case)

    weights = module_weights or {}
    known_test_count = sum(
        len(module_cases)
        for module, module_cases in modules.items()
        if module in weights
    )
    known_seconds = sum(
        weights[module]
        for module in modules
        if module in weights
    )
    fallback_seconds_per_test = (
        known_seconds / known_test_count
        if known_test_count and known_seconds > 0
        else 1.0
    )

    def estimated_weight(item: tuple[str, list[unittest.case.TestCase]]) -> float:
        module, module_cases = item
        return weights.get(module, len(module_cases) * fallback_seconds_per_test)

    buckets: list[list[unittest.case.TestCase]] = [[] for _ in range(shard_count)]
    bucket_weights = [0.0] * shard_count

    for module, module_cases in sorted(
        modules.items(),
        key=lambda item: (-estimated_weight(item), item[0]),
    ):
        weight = estimated_weight((module, module_cases))
        target = min(
            range(shard_count),
            key=lambda index: (bucket_weights[index], len(buckets[index]), index),
        )
        buckets[target].extend(module_cases)
        bucket_weights[target] += weight

    return buckets, bucket_weights


class TimingTextTestResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timings: list[TestTiming] = []
        self._started_at = 0.0

    def startTest(self, test):
        self._started_at = time.perf_counter()
        super().startTest(test)

    def stopTest(self, test):
        self.timings.append(
            TestTiming(
                seconds=time.perf_counter() - self._started_at,
                test_id=test.id(),
                module=test.__class__.__module__,
            )
        )
        super().stopTest(test)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one deterministic shard of the unittest verification suite."
    )
    parser.add_argument("--shard-index", type=int, required=True)
    parser.add_argument("--shard-count", type=int, default=2)
    parser.add_argument("--top-slowest", type=int, default=25)
    parser.add_argument("--start-directory", default="tests")
    parser.add_argument(
        "--weights-file",
        type=Path,
        default=ROOT / "tools" / "test_shard_timings.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.shard_count < 1:
        raise SystemExit("--shard-count must be >= 1")
    if args.shard_index < 0 or args.shard_index >= args.shard_count:
        raise SystemExit("--shard-index must be between 0 and shard-count - 1")

    discovered = unittest.defaultTestLoader.discover(args.start_directory)
    cases = list(_iter_test_cases(discovered))
    module_weights = _load_module_weights(args.weights_file)
    shards, predicted_weights = _partition_by_module(
        cases,
        args.shard_count,
        module_weights,
    )
    selected = shards[args.shard_index]
    module_count = len({case.__class__.__module__ for case in selected})

    mode = "duration-weighted" if module_weights else "test-count fallback"
    print(
        f"Verification shard {args.shard_index + 1}/{args.shard_count}: "
        f"{len(selected)} tests across {module_count} modules "
        f"({len(cases)} tests total, {mode})."
    )
    print(
        "Predicted shard weights: "
        + ", ".join(
            f"{index + 1}={weight:.3f}"
            for index, weight in enumerate(predicted_weights)
        )
    )

    runner = unittest.TextTestRunner(
        verbosity=2,
        resultclass=TimingTextTestResult,
    )
    result = runner.run(unittest.TestSuite(selected))

    if result.timings:
        module_seconds: dict[str, float] = defaultdict(float)
        module_tests: dict[str, int] = defaultdict(int)
        for timing in result.timings:
            module_seconds[timing.module] += timing.seconds
            module_tests[timing.module] += 1

        print(f"\nModule timings in shard {args.shard_index + 1}:")
        for module in sorted(module_seconds):
            print(
                "MODULE_TIMING "
                + json.dumps(
                    {
                        "module": module,
                        "seconds": round(module_seconds[module], 6),
                        "tests": module_tests[module],
                    },
                    sort_keys=True,
                )
            )

    if result.timings and args.top_slowest > 0:
        print(f"\nSlowest tests in shard {args.shard_index + 1}:")
        for timing in sorted(
            result.timings,
            key=lambda item: item.seconds,
            reverse=True,
        )[: args.top_slowest]:
            print(f"{timing.seconds:8.3f}s  {timing.test_id}")

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
