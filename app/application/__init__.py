"""Application-service layer for RessourcePlanner.

This package contains orchestration callable from NiceGUI today and from FastAPI
later. Business rules remain in the domain/planning engine; transport and persistence
technologies must not leak into this package.
"""

from .allocation_service import AllocationService
from .commands import (
    DemandApproveCommand,
    DemandCancelCommand,
    DemandCorrectionCommand,
    DemandCreateCommand,
    DemandSubmitCommand,
    DemandUpdateCommand,
    ManualAllocationCreateCommand,
    ManualAllocationDeleteCommand,
    ManualAllocationReleaseCommand,
    ManualAllocationUpdateCommand,
    PlanningRebuildCommand,
    QuickShiftCreateCommand,
    SegmentAssignCommand,
    SegmentCancelCommand,
    SegmentCreateCommand,
    SegmentUpdateCommand,
)
from .command_ports import (
    AllocationCommandPort,
    ApprovedDemandSyncPort,
    PlanningCommandPort,
)
from .errors import (
    ApplicationConflictError,
    ApplicationError,
    ApplicationNotFoundError,
    ApplicationOperationError,
    ApplicationValidationError,
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
    "ApplicationConflictError",
    "ApplicationError",
    "ApplicationNotFoundError",
    "ApplicationOperationError",
    "ApplicationValidationError",
    "ApprovedDemandSyncPort",
    "DemandApproveCommand",
    "DemandCancelCommand",
    "DemandCorrectionCommand",
    "DemandCreateCommand",
    "DemandReadModel",
    "DemandRepositoryPort",
    "DemandSubmitCommand",
    "DemandUpdateCommand",
    "ManualAllocationCreateCommand",
    "ManualAllocationDeleteCommand",
    "ManualAllocationReleaseCommand",
    "ManualAllocationUpdateCommand",
    "PlanningCommandPort",
    "PlanningReadRepositoryPort",
    "PlanningRebuildCommand",
    "PlanningService",
    "QuickShiftCreateCommand",
    "SegmentAssignCommand",
    "SegmentCancelCommand",
    "SegmentCreateCommand",
    "SegmentReadModel",
    "SegmentRepositoryPort",
    "SegmentUpdateCommand",
]
