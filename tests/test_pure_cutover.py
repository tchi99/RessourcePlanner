from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.domain.planning_engine import PlanResult
from app.planning_cutover import rebuild_allocations_pure


class PureCutoverTests(unittest.TestCase):
    @staticmethod
    def _report(*, unsupported: tuple[str, ...] = ()) -> SimpleNamespace:
        result = PlanResult(
            allocations=(),
            segment_count=0,
            locked_allocation_count=0,
            requested_hours=0.0,
            allocated_hours=0.0,
            unallocated_hours=0.0,
            overtime_hours=0.0,
            missing_allocation_count=0,
        )
        return SimpleNamespace(
            shadow_result=result,
            unsupported_segment_ids=unsupported,
        )

    def test_direct_pure_rebuild_persists_without_legacy_checkpoint(self) -> None:
        repo = MagicMock()
        report = self._report()

        with (
            patch("app.planning_cutover.v15_engine.allocation_records", return_value=[]) as snapshot,
            patch("app.planning_cutover.build_shadow_report", return_value=report) as build,
            patch("app.planning_cutover._pure_persistence_rows", return_value=[]) as convert,
            patch("app.planning_cutover.v15_engine._write_allocations") as write,
        ):
            summary = rebuild_allocations_pure(repo)

        snapshot.assert_called_once_with(repo)
        build.assert_called_once_with(repo)
        convert.assert_called_once_with(repo, report)
        write.assert_called_once_with(repo, [])
        self.assertEqual(summary["planning_engine"], "pure")
        self.assertFalse(summary["planning_engine_fallback"])

    def test_unsupported_segment_stops_before_write(self) -> None:
        repo = MagicMock()
        report = self._report(unsupported=("segment",))

        with (
            patch("app.planning_cutover.v15_engine.allocation_records", return_value=[]),
            patch("app.planning_cutover.build_shadow_report", return_value=report),
            patch("app.planning_cutover._pure_persistence_rows") as convert,
            patch("app.planning_cutover.v15_engine._write_allocations") as write,
        ):
            with self.assertRaises(RuntimeError):
                rebuild_allocations_pure(repo)

        convert.assert_not_called()
        write.assert_not_called()

    def test_failed_write_restores_previous_allocation_snapshot(self) -> None:
        repo = MagicMock()
        report = self._report()
        previous = [{"IDAllocation": "previous"}]
        write = MagicMock(side_effect=[RuntimeError("write failed"), None])

        with (
            patch("app.planning_cutover.v15_engine.allocation_records", return_value=previous),
            patch("app.planning_cutover.build_shadow_report", return_value=report),
            patch("app.planning_cutover._pure_persistence_rows", return_value=[]),
            patch("app.planning_cutover.v15_engine._write_allocations", write),
        ):
            with self.assertRaisesRegex(RuntimeError, "write failed"):
                rebuild_allocations_pure(repo)

        self.assertEqual(write.call_count, 2)
        self.assertEqual(write.call_args_list[0].args, (repo, []))
        self.assertEqual(write.call_args_list[1].args, (repo, previous))


if __name__ == "__main__":
    unittest.main()
