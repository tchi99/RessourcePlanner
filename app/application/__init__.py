"""Application-service layer for RessourcePlanner.

This package exposes the stable transport-neutral application surface. NiceGUI today
and FastAPI later should depend on commands/results/facade rather than persistence or
historical implementation modules.
"""

from .allocation_service import AllocationService
from .commands import (
    DemandAlternativeSelectCommand,
    DemandApproveCommand,
    DemandCancelCommand,
    DemandCorrectionCommand,
    DemandCreateCommand,
    DemandPeriodInput,
    DemandPeriodsReplaceCommand,
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
from .idempotency import (
    CommandIdempotencyPort,
    IdempotentCommandExecutor,
    normalize_idempotency_key,
    request_fingerprint,
)
from .planning_service import PlanningService
from .query_models import (
    PendingDemandLoadReadModel,
    PlanningSnapshotReadModel,
    ProjectReadModel,
    ResourceReadModel,
    ShiftReadModel,
    WorkPackageReadModel,
)
from .query_ports import PlannerQueryPort
from .read_models import DemandPeriodReadModel, DemandReadModel, SegmentReadModel
from .repository_ports import (
    DemandPeriodRepositoryPort,
    DemandRepositoryPort,
    PlanningReadRepositoryPort,
    SegmentRepositoryPort,
)
from .results import (
    AllocationMutationResult,
    ApplicationResult,
    DemandAlternativeSelectionResult,
    DemandMutationResult,
    DemandPeriodsMutationResult,
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
    "CommandIdempotencyPort",
    "DemandAlternativeSelectCommand",
    "DemandAlternativeSelectionResult",
    "DemandApproveCommand",
    "DemandCancelCommand",
    "DemandCorrectionCommand",
    "DemandCreateCommand",
    "DemandMutationResult",
    "DemandPeriodInput",
    "DemandPeriodReadModel",
    "DemandPeriodRepositoryPort",
    "DemandPeriodsMutationResult",
    "DemandPeriodsReplaceCommand",
    "DemandReadModel",
    "DemandRepositoryPort",
    "DemandSubmitCommand",
    "DemandUpdateCommand",
    "IdempotentCommandExecutor",
    "ManualAllocationCreateCommand",
    "ManualAllocationDeleteCommand",
    "ManualAllocationReleaseCommand",
    "ManualAllocationUpdateCommand",
    "PendingDemandLoadReadModel",
    "PlannerQueryPort",
    "PlanningCommandPort",
    "PlanningReadRepositoryPort",
    "PlanningRebuildCommand",
    "PlanningResult",
    "PlanningService",
    "PlanningSnapshotReadModel",
    "ProjectReadModel",
    "QuickShiftCreateCommand",
    "QuickShiftCreatedResult",
    "ResourceReadModel",
    "SegmentAssignCommand",
    "SegmentCancelCommand",
    "SegmentCreateCommand",
    "SegmentMutationResult",
    "SegmentReadModel",
    "SegmentRepositoryPort",
    "SegmentUpdateCommand",
    "ShiftReadModel",
    "WorkPackageReadModel",
    "normalize_idempotency_key",
    "request_fingerprint",
]
