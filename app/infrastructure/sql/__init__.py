"""SQL-backed persistence foundation for RessourcePlanner.

This package contains database infrastructure only. Application services and the pure
planning engine must continue to depend on ports/read models rather than SQLAlchemy.
"""

from .base import Base, NAMING_CONVENTION, new_id
from .demand_repository import SqlDemandRepository
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
from .segment_repository import SqlSegmentRepository
from .session import (
    SqlSessionFactory,
    create_session_factory,
    create_sql_engine,
    transactional_session,
)

__all__ = [
    "Base",
    "NAMING_CONVENTION",
    "ORIGIN_AD_HOC",
    "ORIGIN_QUICK_SHIFT",
    "ORIGIN_REQUEST",
    "Project",
    "Resource",
    "ResourceAvailabilityRule",
    "ResourceRequirement",
    "Shift",
    "SqlDemandRepository",
    "SqlSegmentRepository",
    "SqlSessionFactory",
    "WorkPackage",
    "WorkforceRequest",
    "WorkforceRequestHistory",
    "create_session_factory",
    "create_sql_engine",
    "new_id",
    "transactional_session",
]
