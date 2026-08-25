from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .common import date_value, float_value, required_text, text


@dataclass(frozen=True, slots=True)
class QuickShiftCreateCommand:
    project_number: str
    technician: str
    day: date
    hours: float
    project_name: str = ""
    outside_standard_hours: bool = False
    note: str = ""
    description: str = ""

    @classmethod
    def from_values(
        cls,
        *,
        project_number: object,
        technician: object,
        day_value: object,
        hours_value: object,
        project_name: object = "",
        outside_standard_hours: bool = False,
        note: str = "",
        description: str = "",
    ) -> "QuickShiftCreateCommand":
        return cls(
            project_number=required_text(
                project_number,
                field="quick_shift_project",
                message="Un projet est requis pour le quart rapide.",
            ),
            technician=required_text(
                technician,
                field="quick_shift_resource",
                message="Une ressource est requise pour le quart rapide.",
            ),
            day=date_value(day_value, field="quick_shift_day", required=True),  # type: ignore[arg-type]
            hours=float_value(
                hours_value,
                field="quick_shift_hours",
                required=True,
                minimum=0.01,
            ),  # type: ignore[arg-type]
            project_name=text(project_name),
            outside_standard_hours=bool(outside_standard_hours),
            note=str(note or "").strip(),
            description=str(description or "").strip(),
        )
