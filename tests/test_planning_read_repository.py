from __future__ import annotations

import ast
from contextlib import contextmanager
from pathlib import Path
import unittest

from app.domain.planning_snapshot import PlanningSnapshot
from app.infrastructure.excel.planning_repository import (
    ExcelPlanningReadRepository,
    PlanningSourceReadError,
)
from app.planning_shadow import build_planning_snapshot, build_shadow_report_from_repository


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


class PlanningReadRepositoryTests(unittest.TestCase):
    def test_build_planning_snapshot_calls_reader_once(self) -> None:
        expected = PlanningSnapshot.capture(
            segments=[{"IDSegment": "S1"}],
            demands=[{"NoDemande": "D1"}],
            allocations=[],
            availability=[],
            technicians=[],
        )

        class Reader:
            calls = 0

            def capture(self):
                self.calls += 1
                return expected

        reader = Reader()
        actual = build_planning_snapshot(reader)

        self.assertIs(actual, expected)
        self.assertEqual(reader.calls, 1)

    def test_excel_reader_captures_all_sources_under_one_lock(self) -> None:
        events: list[object] = []

        class FakeExcelRepository:
            @contextmanager
            def _lock_context(self):
                events.append("lock-enter")
                try:
                    yield
                finally:
                    events.append("lock-exit")

            def __init__(self):
                self._lock = self._lock_context()

            def _sheet_as_records(self, sheet, header):
                events.append((sheet, header))
                fixtures = {
                    "SegmentsMO": [{"IDSegment": "S1"}],
                    "DemandesMO": [{"NoDemande": "D1"}],
                    "AllocationsMO": [{"IDAllocation": "A1"}],
                    "Disponibilites": [{"ID": "AV1"}],
                }
                return fixtures[sheet]

            def technicians(self):
                events.append("technicians")
                return [{"name": "R1"}]

        snapshot = ExcelPlanningReadRepository(FakeExcelRepository()).capture()

        self.assertEqual(events[0], "lock-enter")
        self.assertEqual(events[-1], "lock-exit")
        self.assertEqual(
            [event[0] for event in events if isinstance(event, tuple)],
            ["SegmentsMO", "DemandesMO", "AllocationsMO", "Disponibilites"],
        )
        self.assertEqual(snapshot.segments[0]["IDSegment"], "S1")
        self.assertEqual(snapshot.demands[0]["NoDemande"], "D1")
        self.assertEqual(snapshot.allocations[0]["IDAllocation"], "A1")
        self.assertEqual(snapshot.availability[0]["ID"], "AV1")
        self.assertEqual(snapshot.technicians[0]["name"], "R1")

    def test_excel_reader_fails_closed_when_allocations_cannot_be_read(self) -> None:
        class FakeLock:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        class FakeExcelRepository:
            def __init__(self):
                self._lock = FakeLock()

            def _sheet_as_records(self, sheet, header):
                if sheet == "AllocationsMO":
                    raise RuntimeError("COM read failed")
                fixtures = {
                    "SegmentsMO": [{"IDSegment": "S1"}],
                    "DemandesMO": [{"NoDemande": "D1"}],
                    "Disponibilites": [{"ID": "AV1"}],
                }
                return fixtures[sheet]

            def technicians(self):
                return [{"name": "R1"}]

        with self.assertRaises(PlanningSourceReadError) as ctx:
            ExcelPlanningReadRepository(FakeExcelRepository()).capture()

        self.assertEqual(ctx.exception.sheet, "AllocationsMO")
        self.assertIn("recalcul est annulé", str(ctx.exception))

    def test_shadow_report_repository_path_captures_once(self) -> None:
        snapshot = PlanningSnapshot.capture(
            segments=[],
            demands=[],
            allocations=[],
            availability=[],
            technicians=[],
        )

        class Reader:
            calls = 0

            def capture(self):
                self.calls += 1
                return snapshot

        reader = Reader()
        report = build_shadow_report_from_repository(reader)

        self.assertEqual(reader.calls, 1)
        self.assertEqual(report.shadow_result.segment_count, 0)
        self.assertEqual(report.unsupported_segment_ids, ())

    def test_planning_shadow_does_not_import_excel_storage(self) -> None:
        source = (APP / "planning_shadow.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module or "")

        self.assertNotIn("excel_repository", imports)
        self.assertNotIn("app.excel_repository", imports)
        self.assertNotIn("xlwings", imports)
        self.assertNotIn("_sheet_as_records", source)
        self.assertNotIn('"SegmentsMO"', source)
        self.assertIn("PlanningReadRepositoryPort", source)
        self.assertIn("reader.capture()", source)

    def test_excel_adapter_owns_physical_planning_sources(self) -> None:
        source = (
            APP / "infrastructure" / "excel" / "planning_repository.py"
        ).read_text(encoding="utf-8")

        for sheet in (
            "SegmentsMO",
            "DemandesMO",
            "AllocationsMO",
            "Disponibilites",
        ):
            self.assertIn(f'"{sheet}"', source)
        self.assertIn("self._repository.technicians()", source)
        self.assertIn("PlanningSnapshot.capture(", source)
        self.assertNotIn("import xlwings", source)

    def test_cutover_uses_excel_planning_reader_explicitly(self) -> None:
        source = (APP / "planning_cutover.py").read_text(encoding="utf-8")

        self.assertIn("ExcelPlanningReadRepository", source)
        self.assertIn(
            "build_planning_snapshot(ExcelPlanningReadRepository(repo))",
            source,
        )


if __name__ == "__main__":
    unittest.main()
