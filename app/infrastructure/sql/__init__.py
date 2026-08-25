"""SQL-backed persistence foundation for RessourcePlanner.

This package contains database infrastructure only. Application services and the pure
planning engine must continue to depend on ports/read models rather than SQLAlchemy.
"""

from .base import Base, NAMING_CONVENTION, new_id
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
    "WorkPackage",
    "WorkforceRequest",
    "WorkforceRequestHistory",
    "new_id",
]
