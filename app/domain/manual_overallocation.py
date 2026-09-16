from __future__ import annotations

from dataclasses import dataclass


KEEP_EXCEPTION = "KEEP_EXCEPTION"
INCREASE_PLANNED = "INCREASE_PLANNED"
VALID_OVERALLOCATION_POLICIES = frozenset({KEEP_EXCEPTION, INCREASE_PLANNED})
TOLERANCE_HOURS = 0.001


@dataclass(frozen=True, slots=True)
class ManualOverallocationImpact:
    planned_hours: float
    current_locked_hours: float
    projected_locked_hours: float
    current_excess_hours: float
    projected_excess_hours: float

    @property
    def increases_exception(self) -> bool:
        return self.projected_excess_hours > self.current_excess_hours + TOLERANCE_HOURS

    @property
    def has_exception(self) -> bool:
        return self.projected_excess_hours > TOLERANCE_HOURS


def manual_overallocation_impact(
    *,
    planned_hours: float,
    current_locked_hours: float,
    projected_locked_hours: float,
) -> ManualOverallocationImpact:
    planned = max(float(planned_hours), 0.0)
    current = max(float(current_locked_hours), 0.0)
    projected = max(float(projected_locked_hours), 0.0)
    return ManualOverallocationImpact(
        planned_hours=round(planned, 2),
        current_locked_hours=round(current, 2),
        projected_locked_hours=round(projected, 2),
        current_excess_hours=round(max(current - planned, 0.0), 2),
        projected_excess_hours=round(max(projected - planned, 0.0), 2),
    )


def normalize_overallocation_policy(value: object) -> str | None:
    if value in (None, ""):
        return None
    normalized = str(value).strip().upper()
    if normalized not in VALID_OVERALLOCATION_POLICIES:
        raise ValueError(
            "La politique de surallocation doit être KEEP_EXCEPTION ou INCREASE_PLANNED."
        )
    return normalized
