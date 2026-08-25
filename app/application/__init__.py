"""Application-service layer for RessourcePlanner.

This package contains orchestration callable from NiceGUI today and from FastAPI
later. Business rules remain in the domain/planning engine; transport and persistence
technologies must not leak into this package.
"""

from .allocation_service import AllocationService
from .command_ports import (
    AllocationCommandPort,
    ApprovedDemandSyncPort,
    PlanningCommandPort,
)
from .planning_service import PlanningService
from .read_models import DemandReadModel, SegmentReadModel
from .repository_ports import (
    DemandRepositoryPort,
    PlanningReadRepositoryPort,
    SegmentRepositoryPort,
)

__all__ = [
    "AllocationCommandPort",
    "AllocationService",
    "ApprovedDemandSyncPort",
    "DemandReadModel",
    "DemandRepositoryPort",
    "PlanningCommandPort",
    "PlanningReadRepositoryPort",
    "PlanningService",
    "SegmentReadModel",
    "SegmentRepositoryPort",
]
