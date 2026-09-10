from __future__ import annotations

from dataclasses import dataclass

from .confirmation import CONFIRMATION_CONFIRMED, normalize_confirmation


LOAD_FIRM = "FIRM"
LOAD_POTENTIAL = "POTENTIAL"
PENDING_LOAD_ADDITIVE = "ADDITIVE"
PENDING_LOAD_REPLACEMENT = "REPLACEMENT"


def workload_kind(confirmation: object | None) -> str:
    """Classify workload without coupling capacity semantics to a UI or storage layer.

    Confirmed work is firm. Every other valid confirmation state is potential. A blank
    value remains backward-compatible and is treated as the historical confirmed
    default; callers that support inheritance should resolve it before classification.
    """

    normalized = normalize_confirmation(confirmation, default=CONFIRMATION_CONFIRMED)
    return LOAD_FIRM if normalized == CONFIRMATION_CONFIRMED else LOAD_POTENTIAL


def pending_load_mode(*, has_current_plan: bool) -> str:
    """Describe whether a submitted proposal adds load or replaces an approved plan."""

    return PENDING_LOAD_REPLACEMENT if has_current_plan else PENDING_LOAD_ADDITIVE


@dataclass(frozen=True, slots=True)
class WorkloadTotals:
    """Mutually exclusive firm/potential hours for one capacity bucket."""

    firm_hours: float = 0.0
    potential_hours: float = 0.0

    @property
    def exposure_hours(self) -> float:
        return round(self.firm_hours + self.potential_hours, 2)

    def add(self, hours: float, confirmation: object | None) -> "WorkloadTotals":
        value = max(float(hours or 0.0), 0.0)
        if workload_kind(confirmation) == LOAD_FIRM:
            return WorkloadTotals(
                firm_hours=round(self.firm_hours + value, 2),
                potential_hours=self.potential_hours,
            )
        return WorkloadTotals(
            firm_hours=self.firm_hours,
            potential_hours=round(self.potential_hours + value, 2),
        )
