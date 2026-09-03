from __future__ import annotations

from sqlalchemy.orm import Session

from ..application import (
    AllocationService,
    ApplicationFacade,
    PlannerQueryPort,
    PlanningService,
)
from ..application.demand_service import DemandService
from ..application.quick_shift_service import QuickShiftService
from ..application.segment_service import SegmentService
from ..infrastructure.sql import (
    SqlAllocationCommandAdapter,
    SqlDemandPeriodRepository,
    SqlDemandRepository,
    SqlPeriodAwareApprovedDemandSyncAdapter,
    SqlPlannerQueryRepository,
    SqlPlanningCommandAdapter,
    SqlSegmentRepository,
)


def build_sql_facade(
    session: Session,
    *,
    actor_name: str = "api",
) -> ApplicationFacade:
    """Compose one application facade inside the caller-owned SQL transaction."""

    actor = str(actor_name or "api").strip() or "api"
    demands = SqlDemandRepository(session, actor_name=actor)
    periods = SqlDemandPeriodRepository(session, actor_name=actor)
    segments = SqlSegmentRepository(session)
    planning_commands = SqlPlanningCommandAdapter(session)
    allocation_commands = SqlAllocationCommandAdapter(
        session,
        planning=planning_commands,
    )
    approved_sync = SqlPeriodAwareApprovedDemandSyncAdapter(session)

    return ApplicationFacade(
        demands=DemandService(
            demands,
            planning_commands,
            approved_sync,
            periods=periods,
            current_user=actor,
        ),
        segments=SegmentService(segments, planning_commands),
        allocations=AllocationService(allocation_commands),
        quick_shifts=QuickShiftService(segments, allocation_commands),
        planning=PlanningService(planning_commands),
    )


def build_sql_query_port(session: Session) -> PlannerQueryPort:
    """Compose the canonical read-only query port for one request transaction."""

    return SqlPlannerQueryRepository(session)
