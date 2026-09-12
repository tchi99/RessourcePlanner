"""SQL-backed persistence foundation for RessourcePlanner.

This package contains database infrastructure only. Application services and the pure
planning engine must continue to depend on ports/read models rather than SQLAlchemy.
"""

from .base import Base, NAMING_CONVENTION, new_id
from .command_adapters import (
    SqlAllocationCommandAdapter,
    SqlApprovedDemandSyncAdapter,
    SqlPlanningCommandAdapter,
)
from .demand_period_models import (
    WorkforceRequestPeriod,
    WorkforceRequestPeriodRequirement,
    WorkforceRequestPeriodSelection,
)
from .demand_period_repository import SqlDemandPeriodRepository
from .demand_repository import SqlDemandRepository
from .idempotency import CommandIdempotencyReceipt, SqlCommandIdempotencyAdapter
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
from .period_approved_sync import SqlPeriodAwareApprovedDemandSyncAdapter
from .planning_repository import SqlPlanningReadRepository
from .query_repository import SqlPlannerQueryRepository
from .segment_repository import SqlSegmentRepository
from .session import (
    SqlSessionFactory,
    create_session_factory,
    create_sql_engine,
    transactional_session,
)
from .work_package_repository import SqlWorkPackageRepository

__all__ = [
    "Base",
    "CommandIdempotencyReceipt",
    "NAMING_CONVENTION",
    "ORIGIN_AD_HOC",
    "ORIGIN_QUICK_SHIFT",
    "ORIGIN_REQUEST",
    "Project",
    "RESOURCE_REQUIREMENT_NUMBER_INDEX",
    "Resource",
    "ResourceAvailabilityRule",
    "ResourceRequirement",
    "Shift",
    "SqlAllocationCommandAdapter",
    "SqlApprovedDemandSyncAdapter",
    "SqlCommandIdempotencyAdapter",
    "SqlDemandPeriodRepository",
    "SqlDemandRepository",
    "SqlPeriodAwareApprovedDemandSyncAdapter",
    "SqlPlannerQueryRepository",
    "SqlPlanningCommandAdapter",
    "SqlPlanningReadRepository",
    "SqlSegmentRepository",
    "SqlSessionFactory",
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
