from __future__ import annotations

from typing import Any

from ...application.repository_ports import PlanningReadRepositoryPort
from ...domain.planning_snapshot import PlanningSnapshot


class PlanningSourceReadError(RuntimeError):
    """A required planning source could not be read safely."""

    def __init__(self, sheet: str, expected_header: str) -> None:
        self.sheet = sheet
        self.expected_header = expected_header
        super().__init__(
            f"Impossible de lire la source de planification {sheet} "
            f"(en-tête attendu: {expected_header}). Le recalcul est annulé afin de préserver les données existantes."
        )


class ExcelPlanningReadRepository(PlanningReadRepositoryPort):
    """Capture one coherent planning snapshot from the current Excel repository.

    Workbook locking and physical sheet names belong here, not in the planning
    calculation module. The adapter is duck-typed so importing it does not load
    xlwings; the concrete runtime object is the current ExcelRepository.

    Required planning sources are fail-closed: a transient Excel read error must never
    be converted to an empty collection because a subsequent rebuild would otherwise
    interpret that as authoritative absence and could overwrite persisted decisions.
    """

    def __init__(self, repository: Any) -> None:
        self._repository = repository

    def _records(self, sheet: str, expected_header: str) -> list[dict[str, Any]]:
        try:
            return self._repository._sheet_as_records(sheet, expected_header)
        except Exception as exc:
            raise PlanningSourceReadError(sheet, expected_header) from exc

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
