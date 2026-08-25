"""Application-service layer for RessourcePlanner.

This package contains orchestration that can be called from NiceGUI today and from
FastAPI adapters later. Business rules remain in the domain/planning engine;
transport and persistence technologies must not leak into this package.
"""

from .allocation_service import AllocationService
from .planning_service import PlanningService
from .read_models import DemandReadModel, SegmentReadModel
from .repository_ports import (
    DemandRepositoryPort,
    PlanningReadRepositoryPort,
    SegmentRepositoryPort,
)

__all__ = [
    "AllocationService",
    "PlanningService",
    "DemandReadModel",
    "SegmentReadModel",
    "DemandRepositoryPort",
    "PlanningReadRepositoryPort",
    "SegmentRepositoryPort",
]
