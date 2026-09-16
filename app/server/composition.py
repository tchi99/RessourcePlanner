from __future__ import annotations

from sqlalchemy.orm import Session

from ..application import (
    AllocationService,
    ApplicationFacade,
    EmergencyApplicationFacade,
    EmergencyDemandService,
    IdempotentCommandExecutor,
    PlannerQueryPort,
    PlanningService,
    ResourceAdminService,
    WorkPackageService,
)
from ..application.communications import CommunicationService, CommunicationTransportPort
from ..application.quick_shift_service import QuickShiftService
from ..application.segment_service import SegmentService
from ..application.user_admin import UserAdminService
from ..infrastructure.sql import (
    SqlAllocationCommandAdapter,
    SqlCommandIdempotencyAdapter,
    SqlDemandPeriodRepository,
    SqlEmergencyDemandRepository,
    SqlPeriodAwareApprovedDemandSyncAdapter,
    SqlPlannerQueryRepositoryWithEmergencyOverride,
    SqlPlanningCommandAdapter,
    SqlResourceAdminRepository,
    SqlSegmentRepository,
    SqlUserIdentityRepository,
    SqlWorkPackageRepository,
)
from ..infrastructure.sql.communication_repository import SqlCommunicationRepository
from ..infrastructure.sql.planning_audit import (
    AuditedAllocationCommandAdapter,
    AuditedApprovedDemandSyncAdapter,
    AuditedSegmentRepository,
    SqlPlanningAuditJournal,
)


def build_sql_facade(
    session: Session,
    *,
    actor_name: str = "api",
) -> ApplicationFacade:
    """Compose one application facade inside the caller-owned SQL transaction."""

    actor = str(actor_name or "api").strip() or "api"
    journal = SqlPlanningAuditJournal(session, actor_name=actor)
    demands = SqlEmergencyDemandRepository(session, actor_name=actor)
    periods = SqlDemandPeriodRepository(session, actor_name=actor)
    segments = AuditedSegmentRepository(
        SqlSegmentRepository(session, actor_name=actor),
        journal,
    )
    work_packages = SqlWorkPackageRepository(session)
    resources = SqlResourceAdminRepository(session)
    planning_commands = SqlPlanningCommandAdapter(session)
    allocation_commands = AuditedAllocationCommandAdapter(
        SqlAllocationCommandAdapter(
            session,
            planning=planning_commands,
        ),
        journal,
    )
    approved_sync = AuditedApprovedDemandSyncAdapter(
        SqlPeriodAwareApprovedDemandSyncAdapter(session),
        journal,
    )

    return EmergencyApplicationFacade(
        demands=EmergencyDemandService(
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
        work_packages=WorkPackageService(work_packages),
        resource_admin=ResourceAdminService(resources),
    )


def build_sql_idempotency_executor(
    session: Session,
    *,
    actor_name: str = "api",
) -> IdempotentCommandExecutor:
    """Compose durable command replay inside the same transaction as the facade."""

    actor = str(actor_name or "api").strip() or "api"
    return IdempotentCommandExecutor(
        SqlCommandIdempotencyAdapter(session, actor_name=actor)
    )


def build_sql_query_port(session: Session) -> PlannerQueryPort:
    """Compose the canonical read-only query port for one request transaction."""

    return SqlPlannerQueryRepositoryWithEmergencyOverride(session)


def build_user_admin_service(session: Session) -> UserAdminService:
    """Compose local identity administration inside the request transaction."""

    return UserAdminService(SqlUserIdentityRepository(session))


def build_communication_service(
    session: Session,
    *,
    transport: CommunicationTransportPort | None = None,
) -> CommunicationService:
    """Compose controlled communication preparation and explicit external draft creation."""

    return CommunicationService(SqlCommunicationRepository(session), transport=transport)