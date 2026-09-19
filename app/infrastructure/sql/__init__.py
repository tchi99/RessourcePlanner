"""SQL-backed persistence foundation for RessourcePlanner.

This package contains database infrastructure only. Application services and the pure
planning engine must continue to depend on ports/read models rather than SQLAlchemy.
"""

from .active_days_query_repository import (
    SqlPlannerQueryRepositoryWithEstimatedDays,
    SqlSegmentRepositoryWithActiveDayMetrics,
)
from .auth_session_repository import LoginTransactionRecord, SqlAuthSessionRepository
from .base import Base, NAMING_CONVENTION, new_id
from .command_adapters import (
    SqlAllocationCommandAdapter,
    SqlApprovedDemandSyncAdapter,
    SqlPlanningCommandAdapter,
)
from .communication_models import (
    CommunicationBatchRow,
    CommunicationContact,
    CommunicationMessageRow,
    CommunicationSnapshotLine,
)
from .communication_repository import SqlCommunicationRepository
from .competency_catalog_repository import SqlCompetencyCatalogRepository
from .demand_period_models import (
    WorkforceRequestPeriod,
    WorkforceRequestPeriodRequirement,
    WorkforceRequestPeriodSelection,
)
from .demand_period_repository import SqlDemandPeriodRepository
from .demand_repository import SqlDemandRepository
from .emergency_demand_repository import SqlEmergencyDemandRepository
from .emergency_query_repository import SqlPlannerQueryRepositoryWithEmergencyOverride
from .employee_sync_repository import SqlEmployeeSyncRepository
from .idempotency import CommandIdempotencyReceipt, SqlCommandIdempotencyAdapter
from .identity_models import AppUser, AuthLoginTransaction, AuthSession
from .identity_repository import SqlUserIdentityRepository
from .identity_resource_link_repository import SqlIdentityResourceLinkRepository
from .load_profile_audit import LoadProfileAuditedSegmentRepository
from .load_profile_query_repository import SqlPlannerQueryRepositoryWithLoadProfiles
from .models import (
    ORIGIN_AD_HOC,
    ORIGIN_QUICK_SHIFT,
    ORIGIN_REQUEST,
    Competency,
    Project,
    Resource,
    ResourceCompetency,
    TaskCatalogEntry,
    ResourceAvailabilityRule,
    ResourceRequirement,
    Shift,
    WorkforceRequest,
    WorkforceRequestCompetency,
    WorkforceRequestHistory,
    WorkPackage,
)
from .identity_constraints import (
    RESOURCE_REQUIREMENT_NUMBER_INDEX,
    WORKFORCE_REQUEST_NUMBER_INDEX,
)
from .resource_identity_constraints import RESOURCE_EXTERNAL_ID_INDEX
from .period_approved_sync import SqlPeriodAwareApprovedDemandSyncAdapter
from .planning_audit import PlanningChangeHistory
from .planning_repository import SqlPlanningReadRepository
from .capacity_query_repository import SqlPlannerQueryRepository
from .project_sync_repository import SqlProjectSyncRepository
from .task_catalog_repository import SqlTaskCatalogRepository
from .resource_admin_repository import SqlResourceAdminRepository
from .segment_repository import SqlSegmentRepository
from .overallocation import (
    OverallocationAuditedAllocationCommandAdapter,
    OverallocationAuditedSegmentRepository,
    SqlOverallocationAllocationCommandAdapter,
    SqlPlannerQueryRepositoryWithOverallocation,
    SqlSegmentRepositoryWithAllocationMetrics,
)
from .session import (
    SqlSessionFactory,
    create_session_factory,
    create_sql_engine,
    transactional_session,
)
from .work_package_repository import SqlWorkPackageRepository

__all__ = [
    "AppUser",
    "AuthLoginTransaction",
    "AuthSession",
    "Base",
    "CommandIdempotencyReceipt",
    "Competency",
    "CommunicationBatchRow",
    "CommunicationContact",
    "CommunicationMessageRow",
    "CommunicationSnapshotLine",
    "LoadProfileAuditedSegmentRepository",
    "LoginTransactionRecord",
    "NAMING_CONVENTION",
    "ORIGIN_AD_HOC",
    "ORIGIN_QUICK_SHIFT",
    "ORIGIN_REQUEST",
    "OverallocationAuditedAllocationCommandAdapter",
    "OverallocationAuditedSegmentRepository",
    "PlanningChangeHistory",
    "Project",
    "RESOURCE_EXTERNAL_ID_INDEX",
    "RESOURCE_REQUIREMENT_NUMBER_INDEX",
    "Resource",
    "ResourceAvailabilityRule",
    "ResourceCompetency",
    "ResourceRequirement",
    "Shift",
    "TaskCatalogEntry",
    "SqlAllocationCommandAdapter",
    "SqlApprovedDemandSyncAdapter",
    "SqlAuthSessionRepository",
    "SqlCommandIdempotencyAdapter",
    "SqlCommunicationRepository",
    "SqlCompetencyCatalogRepository",
    "SqlDemandPeriodRepository",
    "SqlDemandRepository",
    "SqlEmergencyDemandRepository",
    "SqlEmployeeSyncRepository",
    "SqlIdentityResourceLinkRepository",
    "SqlOverallocationAllocationCommandAdapter",
    "SqlPeriodAwareApprovedDemandSyncAdapter",
    "SqlPlannerQueryRepository",
    "SqlPlannerQueryRepositoryWithEmergencyOverride",
    "SqlPlannerQueryRepositoryWithEstimatedDays",
    "SqlPlannerQueryRepositoryWithLoadProfiles",
    "SqlPlannerQueryRepositoryWithOverallocation",
    "SqlPlanningCommandAdapter",
    "SqlPlanningReadRepository",
    "SqlProjectSyncRepository",
    "SqlTaskCatalogRepository",
    "SqlResourceAdminRepository",
    "SqlSegmentRepository",
    "SqlSegmentRepositoryWithActiveDayMetrics",
    "SqlSegmentRepositoryWithAllocationMetrics",
    "SqlSessionFactory",
    "SqlUserIdentityRepository",
    "SqlWorkPackageRepository",
    "WORKFORCE_REQUEST_NUMBER_INDEX",
    "WorkPackage",
    "WorkforceRequest",
    "WorkforceRequestCompetency",
    "WorkforceRequestHistory",
    "WorkforceRequestPeriod",
    "WorkforceRequestPeriodRequirement",
    "WorkforceRequestPeriodSelection",
    "create_session_factory",
    "create_sql_engine",
    "new_id",
    "transactional_session",
]
