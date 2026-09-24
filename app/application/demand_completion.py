from __future__ import annotations

from dataclasses import dataclass, replace

from .read_models import DemandReadModel


COMPLETED_EFFECTIVE_STATUS = "Complétée"
CANCELLED_STATUS = "Annulée"
ACTIVE_PLANNING_STATUS = "En planification"


@dataclass(frozen=True, slots=True)
class DemandCompletionFacts:
    """Read-side facts required to derive terminal completion without mutation."""

    human_requirement_count: int = 0
    human_remaining_requirement_count: int = 0
    current_or_future_shift_count: int = 0
    asset_requirement_count: int = 0
    asset_uncovered_requirement_count: int = 0
    current_or_future_asset_allocation_count: int = 0

    @property
    def has_materialized_plan(self) -> bool:
        return self.human_requirement_count > 0 or self.asset_requirement_count > 0


def project_effective_demand_state(
    demand: DemandReadModel,
    facts: DemandCompletionFacts,
) -> DemandReadModel:
    """Project list/detail terminal state from the active materialized plan.

    The persisted workflow status remains authoritative for commands. Completion is
    deliberately read-only: dates on the candidate request never complete work on
    their own, and a pending cancellation/reapproval remains visible as active work.
    """

    cancelled = demand.status == CANCELLED_STATUS
    completed = bool(
        not cancelled
        and demand.status == ACTIVE_PLANNING_STATUS
        and demand.cancellation_state != "PENDING"
        and facts.has_materialized_plan
        and facts.human_remaining_requirement_count == 0
        and facts.current_or_future_shift_count == 0
        and facts.asset_uncovered_requirement_count == 0
        and facts.current_or_future_asset_allocation_count == 0
    )
    return replace(
        demand,
        effective_status=(
            COMPLETED_EFFECTIVE_STATUS if completed else demand.status
        ),
        terminal=cancelled or completed,
    )
