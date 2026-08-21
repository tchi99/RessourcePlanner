from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


Row = dict[str, Any]


@dataclass(frozen=True, slots=True)
class PlanningSnapshot:
    """Stable in-memory read model for one planning calculation.

    Row dictionaries are copied when the snapshot is captured so the calculation and
    persistence adapter can reuse exactly the same source state without re-reading the
    workbook. Consumers should treat the row dictionaries as read-only.
    """

    segments: tuple[Row, ...]
    demands: tuple[Row, ...]
    allocations: tuple[Row, ...]
    availability: tuple[Row, ...]
    technicians: tuple[Row, ...]

    @classmethod
    def capture(
        cls,
        *,
        segments: Sequence[Mapping[str, Any]],
        demands: Sequence[Mapping[str, Any]],
        allocations: Sequence[Mapping[str, Any]],
        availability: Sequence[Mapping[str, Any]],
        technicians: Sequence[Mapping[str, Any]],
    ) -> "PlanningSnapshot":
        """Create a snapshot using defensive copies of every source row."""

        def rows(values: Sequence[Mapping[str, Any]]) -> tuple[Row, ...]:
            return tuple(dict(value) for value in values)

        return cls(
            segments=rows(segments),
            demands=rows(demands),
            allocations=rows(allocations),
            availability=rows(availability),
            technicians=rows(technicians),
        )
