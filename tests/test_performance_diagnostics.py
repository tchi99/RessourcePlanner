from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.performance_diagnostics import (
    PerformanceSample,
    append_performance_sample,
    format_performance_report,
    read_performance_samples,
)


class PerformanceDiagnosticsTests(unittest.TestCase):
    def test_sample_contains_only_technical_schema(self) -> None:
        sample = PerformanceSample(
            operation="planning_rebuild",
            status="success",
            total_seconds=1.25,
            read_seconds=0.5,
            compute_seconds=0.01,
            write_seconds=0.6,
            save_seconds=0.14,
            range_reads=5,
            range_writes=2,
            saves=1,
            segment_count=42,
            allocation_output_count=120,
            engine="pure",
        )
        data = sample.to_dict()
        self.assertEqual(data["operation"], "planning_rebuild")
        self.assertEqual(data["engine"], "pure")
        self.assertNotIn("project", data)
        self.assertNotIn("resource", data)
        self.assertNotIn("workbook", data)
        self.assertNotIn("path", data)

    def test_jsonl_round_trip_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "performance.jsonl"
            append_performance_sample(
                PerformanceSample(
                    operation="planning_rebuild",
                    status="success",
                    total_seconds=0.123,
                    compute_seconds=0.004,
                    segment_count=10,
                    allocation_output_count=20,
                    engine="pure",
                ),
                path=path,
            )
            samples = read_performance_samples(path=path, limit=10)
            self.assertEqual(len(samples), 1)
            self.assertEqual(samples[0]["segment_count"], 10)
            report = format_performance_report(samples)
            self.assertIn("planning_rebuild", report)
            self.assertIn("0.123s", report)
            self.assertNotIn("NumeroProjet", report)

    def test_log_rotates_without_breaking_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "performance.jsonl"
            for index in range(12):
                append_performance_sample(
                    PerformanceSample(
                        operation="planning_rebuild",
                        status="success",
                        total_seconds=index / 100,
                        segment_count=index,
                    ),
                    path=path,
                    max_bytes=350,
                    backups=2,
                )
            self.assertTrue(path.exists())
            self.assertTrue(path.with_name("performance.jsonl.1").exists())
            current_lines = path.read_text(encoding="utf-8").splitlines()
            for line in current_lines:
                self.assertIsInstance(json.loads(line), dict)

            samples = read_performance_samples(path=path, limit=50, backups=2)
            self.assertGreater(len(samples), len(current_lines))
            self.assertEqual(samples[-1]["segment_count"], 11)

    def test_negative_timings_and_counters_are_normalized(self) -> None:
        data = PerformanceSample(
            operation="planning_rebuild",
            status="success",
            total_seconds=-1,
            read_seconds=-2,
            range_reads=-5,
        ).to_dict()
        self.assertEqual(data["total_seconds"], 0.0)
        self.assertEqual(data["read_seconds"], 0.0)
        self.assertEqual(data["range_reads"], 0)


if __name__ == "__main__":
    unittest.main()
