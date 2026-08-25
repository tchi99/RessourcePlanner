from __future__ import annotations

from datetime import date
import unittest

from sqlalchemy import func, select

from app.infrastructure.migration import (
    CutoverDataset,
    CutoverExtractionReport,
    CutoverImportError,
    import_cutover_dataset,
)
from app.infrastructure.sql import (
    Base,
    Project,
    create_session_factory,
    create_sql_engine,
    transactional_session,
)


class SqlCutoverImporterGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_sql_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.factory = create_session_factory(self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()

    @staticmethod
    def _report(dataset: CutoverDataset) -> CutoverExtractionReport:
        counts = {
            "projects": len(dataset.projects),
            "work_packages": len(dataset.work_packages),
            "resources": len(dataset.resources),
            "availability": len(dataset.availability),
            "demands": len(dataset.demands),
            "history": len(dataset.history),
            "requirements": len(dataset.requirements),
            "shifts": len(dataset.shifts),
            "locked_shifts": 0,
        }
        hours = {
            "work_package_planned": sum(
                float(row.get("planned_hours") or 0) for row in dataset.work_packages
            ),
            "requirement_planned": 0.0,
            "shift_total": 0.0,
            "locked_shift_total": 0.0,
        }
        return CutoverExtractionReport(
            dataset=dataset,
            diagnostics=(),
            counts=counts,
            hours=hours,
        )

    def test_duplicate_effort_id_aborts_transaction(self) -> None:
        dataset = CutoverDataset(
            projects=({"number": "P1", "name": "Projet"},),
            work_packages=(
                {
                    "legacy_effort_id": "EFF-1",
                    "source_row": 2,
                    "project_number": "P1",
                    "name": "A",
                    "planned_hours": 1,
                },
                {
                    "legacy_effort_id": "EFF-1",
                    "source_row": 3,
                    "project_number": "P1",
                    "name": "B",
                    "planned_hours": 1,
                },
            ),
            resources=(),
            availability=(),
            demands=(),
            history=(),
            requirements=(),
            shifts=(),
        )

        with self.assertRaises(CutoverImportError):
            with transactional_session(self.factory) as session:
                import_cutover_dataset(session, self._report(dataset))

        with self.factory() as session:
            self.assertEqual(
                int(session.scalar(select(func.count()).select_from(Project)) or 0),
                0,
            )

    def test_unknown_demand_effort_link_aborts_transaction(self) -> None:
        dataset = CutoverDataset(
            projects=({"number": "P1", "name": "Projet"},),
            work_packages=(
                {
                    "legacy_effort_id": "EFF-1",
                    "source_row": 2,
                    "project_number": "P1",
                    "name": "A",
                    "planned_hours": 8,
                },
            ),
            resources=(),
            availability=(),
            demands=(
                {
                    "number": "DMO-1",
                    "project_number": "P1",
                    "desired_start": date(2026, 8, 25),
                    "resource_count": 1,
                },
            ),
            history=(),
            requirements=(),
            shifts=(),
        )

        with self.assertRaises(CutoverImportError):
            with transactional_session(self.factory) as session:
                import_cutover_dataset(
                    session,
                    self._report(dataset),
                    demand_work_package_links={"DMO-1": "EFF-UNKNOWN"},
                )

        with self.factory() as session:
            self.assertEqual(
                int(session.scalar(select(func.count()).select_from(Project)) or 0),
                0,
            )


if __name__ == "__main__":
    unittest.main()
