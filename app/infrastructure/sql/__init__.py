"""SQL-backed persistence foundation for RessourcePlanner.

This package contains database infrastructure only. Application services and the pure
planning engine must continue to depend on ports/read models rather than SQLAlchemy.
"""

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
from .demand_period_models import (
    WorkforceRequestPeriod,
    WorkforceRequestPeriodRequirement,
    WorkforceRequestPeriodSelection,
)
from .demand_period_repository import SqlDemandPeriodRepository
from .demand_repository import SqlDemandRepository
from .employee_sync_repository import SqlEmployeeSyncRepository
from .idempotency import CommandIdempotencyReceipt, SqlCommandIdempotencyAdapter
from .identity_models import AppUser, AuthLoginTransaction, AuthSession
from .identity_repository import SqlUserIdentityRepository
from .identity_resource_link_repository import SqlIdentityResourceLinkRepository
from .models import (
    ORIGIN_AD_HOC,
    ORIGIN_QUICK_SHIFT,
    ORIGIN_REQUEST,
    Project,
    Resource,
    ResourceAvailabilityRule,
    ResourceRequirement,
    Shift,
    WorkforceRequest,
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
from .resource_admin_repository import SqlResourceAdminRepository
from .segment_repository import SqlSegmentRepository
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
    "CommunicationBatchRow",
    "CommunicationContact",
    "CommunicationMessageRow",
    "CommunicationSnapshotLine",
    "LoginTransactionRecord",
    "NAMING_CONVENTION",
    "ORIGIN_AD_HOC",
    "ORIGIN_QUICK_SHIFT",
    "ORIGIN_REQUEST",
    "PlanningChangeHistory",
    "Project",
    "RESOURCE_EXTERNAL_ID_INDEX",
    "RESOURCE_REQUIREMENT_NUMBER_INDEX",
    "Resource",
    "ResourceAvailabilityRule",
    "ResourceRequirement",
    "Shift",
    "SqlAllocationCommandAdapter",
    "SqlApprovedDemandSyncAdapter",
    "SqlAuthSessionRepository",
    "SqlCommandIdempotencyAdapter",
    "SqlCommunicationRepository",
    "SqlDemandPeriodRepository",
    "SqlDemandRepository",
    "SqlEmployeeSyncRepository",
    "SqlIdentityResourceLinkRepository",
    "SqlPeriodAwareApprovedDemandSyncAdapter",
    "SqlPlannerQueryRepository",
    "SqlPlanningCommandAdapter",
    "SqlPlanningReadRepository",
    "SqlProjectSyncRepository",
    "SqlResourceAdminRepository",
    "SqlSegmentRepository",
    "SqlSessionFactory",
    "SqlUserIdentityRepository",
    "SqlWorkPackageRepository",
    "WORKFORCE_REQUEST_NUMBER_INDEX",
    "WorkPackage",
    "WorkforceRequest",
    "WorkforceRequestHistory",
    "WorkforceRequestPeriod",
    "WorkforceRequestPeriodRequirement",
    "WorkforceRequestPeriodSelection",
    "create_session_factory",
    "create_sql_engine",
    "new_id",
    "transactional_session",
]
