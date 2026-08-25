"""Application-service layer for RessourcePlanner.

This package exposes the stable transport-neutral application surface. NiceGUI today
and FastAPI later should depend on commands/results/facade rather than persistence or
historical implementation modules.
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
from .facade import ApplicationFacade
from .planning_service import PlanningService
from .read_models import DemandReadModel, SegmentReadModel
from .repository_ports import (
    DemandRepositoryPort,
    PlanningReadRepositoryPort,
    SegmentRepositoryPort,
)
from .results import (
    AllocationMutationResult,
    ApplicationResult,
    DemandMutationResult,
    PlanningResult,
    QuickShiftCreatedResult,
    SegmentMutationResult,
)

__all__ = [
    "AllocationCommandPort",
    "AllocationMutationResult",
    "AllocationService",
    "ApplicationConflictError",
    "ApplicationError",
    "ApplicationFacade",
    "ApplicationNotFoundError",
    "ApplicationOperationError",
    "ApplicationResult",
    "ApplicationValidationError",
    "ApprovedDemandSyncPort",
    "DemandApproveCommand",
    "DemandCancelCommand",
    "DemandCorrectionCommand",
    "DemandCreateCommand",
    "DemandMutationResult",
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
    "PlanningResult",
    "PlanningService",
    "QuickShiftCreateCommand",
    "QuickShiftCreatedResult",
    "SegmentAssignCommand",
    "SegmentCancelCommand",
    "SegmentCreateCommand",
    "SegmentMutationResult",
    "SegmentReadModel",
    "SegmentRepositoryPort",
    "SegmentUpdateCommand",
]
