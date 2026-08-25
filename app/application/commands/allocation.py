from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .common import date_value, float_value, required_text


@dataclass(frozen=True, slots=True)
class ManualAllocationCreateCommand:
    segment_id: str
    technician: str
    day: date
    hours: float
    outside_standard_hours: bool = False
    note: str = ""

    @classmethod
    def from_values(
        cls,
        segment_id: object,
        technician: object,
        day_value: object,
        hours_value: object,
        outside_standard_hours: bool = False,
        note: str = "",
    ) -> "ManualAllocationCreateCommand":
        return cls(
            segment_id=required_text(
                segment_id,
                field="allocation_segment",
                message="Un segment est requis pour le quart manuel.",
            ),
            technician=required_text(
                technician,
                field="allocation_resource",
                message="Un technicien est requis pour le quart manuel.",
            ),
            day=date_value(day_value, field="allocation_day", required=True),  # type: ignore[arg-type]
            hours=float_value(
                hours_value,
                field="allocation_hours",
                required=True,
                minimum=0.01,
            ),  # type: ignore[arg-type]
            outside_standard_hours=bool(outside_standard_hours),
            note=str(note or ""),
        )


@dataclass(frozen=True, slots=True)
class ManualAllocationUpdateCommand:
    allocation_id: str
    technician: str
    day: date
    hours: float
    outside_standard_hours: bool = False
    note: str = ""

    @classmethod
    def from_values(
        cls,
        allocation_id: object,
        technician: object,
        day_value: object,
        hours_value: object,
        outside_standard_hours: bool = False,
        note: str = "",
    ) -> "ManualAllocationUpdateCommand":
        return cls(
            allocation_id=required_text(
                allocation_id,
                field="allocation_id",
                message="Un identifiant d'allocation est requis.",
            ),
            technician=required_text(
                technician,
                field="allocation_resource",
                message="Un technicien est requis pour le quart manuel.",
            ),
            day=date_value(day_value, field="allocation_day", required=True),  # type: ignore[arg-type]
            hours=float_value(
                hours_value,
                field="allocation_hours",
                required=True,
                minimum=0.01,
            ),  # type: ignore[arg-type]
            outside_standard_hours=bool(outside_standard_hours),
            note=str(note or ""),
        )


@dataclass(frozen=True, slots=True)
class ManualAllocationReleaseCommand:
    allocation_id: str


@dataclass(frozen=True, slots=True)
class ManualAllocationDeleteCommand:
    allocation_id: str


@dataclass(frozen=True, slots=True)
class SegmentAssignCommand:
    segment_id: str
    technician: str
