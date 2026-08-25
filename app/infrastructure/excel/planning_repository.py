from __future__ import annotations

from typing import Any

from ...application.repository_ports import PlanningReadRepositoryPort
from ...domain.planning_snapshot import PlanningSnapshot


class ExcelPlanningReadRepository(PlanningReadRepositoryPort):
    """Capture one coherent planning snapshot from the current Excel repository.

    Workbook locking and physical sheet names belong here, not in the planning
    calculation module. The adapter is duck-typed so importing it does not load
    xlwings; the concrete runtime object is the current ExcelRepository.
    """

    def __init__(self, repository: Any) -> None:
        self._repository = repository

    def _records(self, sheet: str, expected_header: str) -> list[dict[str, Any]]:
        try:
            return self._repository._sheet_as_records(sheet, expected_header)
        except Exception:
            return []

    def capture(self) -> PlanningSnapshot:
        with self._repository._lock:
            segments = self._records("SegmentsMO", "IDSegment")
            demands = self._records("DemandesMO", "NoDemande")
            allocations = self._records("AllocationsMO", "IDAllocation")
            availability = self._records("Disponibilites", "ID")
            technicians = self._repository.technicians()

        return PlanningSnapshot.capture(
            segments=segments,
            demands=demands,
            allocations=allocations,
            availability=availability,
            technicians=technicians,
        )
