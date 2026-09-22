from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.orm import Session

from ..application import (
    AllocationService,
    ApplicationFacade,
    BusinessContactAdminService,
    CompetencyCatalogService,
    EmergencyApplicationFacade,
    EmergencyDemandService,
    IdempotentCommandExecutor,
    PlannerQueryPort,
    PlanningService,
    ResourceAdminService,
    WorkPackageService,
)
from ..application.communications import CommunicationService, CommunicationTransportPort
from ..application.operational_contacts import OperationalContactService
from ..application.project_communications import ProjectCommunicationService
from ..application.smtp_settings import (
    SecretCipherPort,
    SmtpClientPort,
    SmtpConfigurationService,
)
from ..application.quick_shift_service import QuickShiftService
from ..application.segment_service import SegmentService
from ..application.user_admin import UserAdminService
from ..application.user_view_context import UserViewContextRepositoryPort
from ..infrastructure.sql import (
    LoadProfileAuditedSegmentRepository,
    OverallocationAuditedAllocationCommandAdapter,
    OverallocationAuditedSegmentRepository,
    SqlBusinessContactAdminRepository,
    SqlCommandIdempotencyAdapter,
    SqlCompetencyCatalogRepository,
    SqlDemandPeriodRepository,
    SqlEmergencyDemandRepository,
    SqlOverallocationAllocationCommandAdapter,
    SqlPeriodAwareApprovedDemandSyncAdapter,
    SqlOperationalContactRepository,
    SqlRequestOperationalChoiceRepository,
    SqlProjectCommunicationRepository,
    SqlPlannerQueryRepositoryWithLoadProfiles,
    SqlPlanningCommandAdapter,
    SqlResourceAdminRepository,
    SqlSmtpConfigurationRepository,
    SqlSegmentRepositoryWithActiveDayMetrics,
    SqlUserIdentityRepository,
    SqlWorkPackageRepository,
)
from ..infrastructure.sql.communication_repository import SqlCommunicationRepository
from ..infrastructure.sql.user_view_context_repository import SqlUserViewContextRepository
from ..infrastructure.sql.emergency_planning_audit import (
    EmergencyAwareApprovedDemandSyncAdapter,
)
from ..infrastructure.sql.planning_audit import (
    AuditedSegmentRepository,
    SqlPlanningAuditJournal,
)


def build_sql_facade(
    session: Session,
    *,
    actor_name: str = "api",
    permissions: Sequence[str] | None = None,
) -> ApplicationFacade:
    """Compose one application facade inside the caller-owned SQL transaction."""

    actor = str(actor_name or "api").strip() or "api"
    journal = SqlPlanningAuditJournal(session, actor_name=actor)
    demands = SqlEmergencyDemandRepository(session, actor_name=actor)
    periods = SqlDemandPeriodRepository(session, actor_name=actor)
    base_segments = SqlSegmentRepositoryWithActiveDayMetrics(session, actor_name=actor)
    segments = OverallocationAuditedSegmentRepository(
        LoadProfileAuditedSegmentRepository(
            AuditedSegmentRepository(base_segments, journal),
            journal,
        ),
        journal,
    )
    work_packages = SqlWorkPackageRepository(session)
    resources = SqlResourceAdminRepository(session)
    planning_commands = SqlPlanningCommandAdapter(session)
    allocation_commands = OverallocationAuditedAllocationCommandAdapter(
        SqlOverallocationAllocationCommandAdapter(
            session,
            planning=planning_commands,
        ),
        journal,
        session,
    )
    approved_sync = EmergencyAwareApprovedDemandSyncAdapter(
        SqlPeriodAwareApprovedDemandSyncAdapter(session),
        journal,
        session,
    )

    return EmergencyApplicationFacade(
        demands=EmergencyDemandService(
            demands,
            planning_commands,
            approved_sync,
            periods=periods,
            operational_choices=SqlRequestOperationalChoiceRepository(
                session,
                actor_name=actor,
            ),
            current_user=actor,
            permissions=permissions,
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

    return SqlPlannerQueryRepositoryWithLoadProfiles(session)


def build_user_admin_service(session: Session) -> UserAdminService:
    """Compose local identity administration inside the request transaction."""

    return UserAdminService(SqlUserIdentityRepository(session))


def build_user_view_context_repository(
    session: Session,
) -> UserViewContextRepositoryPort:
    """Compose stable current-user relationship reads for one request transaction."""

    return SqlUserViewContextRepository(session)


def build_competency_catalog_service(session: Session) -> CompetencyCatalogService:
    """Compose competency catalogue operations inside the request transaction."""

    return CompetencyCatalogService(SqlCompetencyCatalogRepository(session))


def build_communication_service(
    session: Session,
    *,
    transport: CommunicationTransportPort | None = None,
) -> CommunicationService:
    """Compose controlled communication preparation and explicit external draft creation."""

    return CommunicationService(SqlCommunicationRepository(session), transport=transport)


def build_smtp_configuration_service(
    session: Session,
    *,
    cipher: SecretCipherPort | None,
    client: SmtpClientPort,
) -> SmtpConfigurationService:
    """Compose SMTP administration and delivery configuration."""

    return SmtpConfigurationService(
        SqlSmtpConfigurationRepository(session),
        cipher=cipher,
        client=client,
    )


def build_project_communication_service(
    session: Session,
    *,
    transport: CommunicationTransportPort | None = None,
    smtp_service: SmtpConfigurationService | None = None,
) -> ProjectCommunicationService:
    """Compose the #290 project-centric communication projection."""

    operational = OperationalContactService(
        SqlOperationalContactRepository(session)
    )
    return ProjectCommunicationService(
        SqlProjectCommunicationRepository(
            session,
            operational_contacts=operational,
        ),
        workflow_repository=SqlCommunicationRepository(session),
        transport=transport,
        smtp_service=smtp_service,
    )


def build_business_contact_admin_service(
    session: Session,
) -> BusinessContactAdminService:
    """Compose business-contact administration inside the request transaction."""

    return BusinessContactAdminService(SqlBusinessContactAdminRepository(session))
