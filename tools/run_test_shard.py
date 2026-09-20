from __future__ import annotations

import argparse
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


def _iter_test_cases(suite: unittest.TestSuite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _iter_test_cases(item)
        else:
            yield item


def _partition_by_module(
    cases: list[unittest.case.TestCase],
    shard_count: int,
) -> list[list[unittest.case.TestCase]]:
    """Distribute complete test modules across shards with balanced test counts."""

    modules: dict[str, list[unittest.case.TestCase]] = defaultdict(list)
    for case in cases:
        modules[case.__class__.__module__].append(case)

    buckets: list[list[unittest.case.TestCase]] = [[] for _ in range(shard_count)]
    bucket_sizes = [0] * shard_count

    for _module, module_cases in sorted(
        modules.items(),
        key=lambda item: (-len(item[1]), item[0]),
    ):
        target = min(range(shard_count), key=lambda index: (bucket_sizes[index], index))
        buckets[target].extend(module_cases)
        bucket_sizes[target] += len(module_cases)

    return buckets


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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.shard_count < 1:
        raise SystemExit("--shard-count must be >= 1")
    if args.shard_index < 0 or args.shard_index >= args.shard_count:
        raise SystemExit("--shard-index must be between 0 and shard-count - 1")

    discovered = unittest.defaultTestLoader.discover(args.start_directory)
    cases = list(_iter_test_cases(discovered))
    shards = _partition_by_module(cases, args.shard_count)
    selected = shards[args.shard_index]
    module_count = len({case.__class__.__module__ for case in selected})

    print(
        f"Verification shard {args.shard_index + 1}/{args.shard_count}: "
        f"{len(selected)} tests across {module_count} modules "
        f"({len(cases)} tests total)."
    )

    runner = unittest.TextTestRunner(
        verbosity=2,
        resultclass=TimingTextTestResult,
    )
    result = runner.run(unittest.TestSuite(selected))

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
