from __future__ import annotations

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
from .demand_service import DemandService
from .planning_service import PlanningService
from .quick_shift_service import QuickShiftService
from .results import (
    AllocationMutationResult,
    DemandMutationResult,
    PlanningResult,
    QuickShiftCreatedResult,
    SegmentMutationResult,
)
from .segment_service import SegmentService


class ApplicationFacade:
    """Stable use-case surface for UI/API adapters.

    The facade deliberately owns response normalization only. Business orchestration
    remains in the underlying services, while transport adapters consume a uniform set
    of immutable result contracts.
    """

    def __init__(
        self,
        *,
        demands: DemandService,
        segments: SegmentService,
        allocations: AllocationService,
        quick_shifts: QuickShiftService,
        planning: PlanningService,
    ) -> None:
        self._demands = demands
        self._segments = segments
        self._allocations = allocations
        self._quick_shifts = quick_shifts
        self._planning = planning

    def create_demand(self, command: DemandCreateCommand) -> DemandMutationResult:
        number = self._demands.create_command(command)
        return DemandMutationResult(
            demand_number=number,
            status="Soumise" if command.submit else "Brouillon",
        )

    def update_demand(self, command: DemandUpdateCommand) -> DemandMutationResult:
        reapproval = self._demands.modify_command(command)
        return DemandMutationResult(
            demand_number=command.number,
            status="Soumise" if reapproval else None,
            reapproval_required=reapproval,
        )

    def submit_demand(self, command: DemandSubmitCommand) -> DemandMutationResult:
        self._demands.submit_command(command)
        return DemandMutationResult(command.number, status="Soumise")

    def approve_demand(self, command: DemandApproveCommand) -> DemandMutationResult:
        summary = self._demands.approve_command(command)
        return DemandMutationResult(
            command.number,
            status="En planification",
            planning=PlanningResult.from_mapping(summary),
        )

    def request_demand_correction(
        self,
        command: DemandCorrectionCommand,
    ) -> DemandMutationResult:
        self._demands.request_correction_command(command)
        return DemandMutationResult(command.number, status="À corriger")

    def cancel_demand(self, command: DemandCancelCommand) -> DemandMutationResult:
        self._demands.cancel_command(command)
        return DemandMutationResult(command.number, status="Annulée")

    def create_segment(self, command: SegmentCreateCommand) -> SegmentMutationResult:
        identifier, summary = self._segments.create_command(command)
        return SegmentMutationResult(
            segment_id=identifier,
            action="created",
            planning=PlanningResult.from_mapping(summary),
        )

    def update_segment(self, command: SegmentUpdateCommand) -> SegmentMutationResult:
        summary = self._segments.update_command(command)
        return SegmentMutationResult(
            segment_id=command.segment_id,
            action="updated",
            planning=PlanningResult.from_mapping(summary),
        )

    def cancel_segment(self, command: SegmentCancelCommand) -> SegmentMutationResult:
        summary = self._segments.cancel_command(command)
        return SegmentMutationResult(
            segment_id=command.segment_id,
            action="cancelled",
            planning=PlanningResult.from_mapping(summary),
        )

    def assign_segment(self, command: SegmentAssignCommand) -> SegmentMutationResult:
        summary = self._allocations.assign_segment_command(command)
        return SegmentMutationResult(
            segment_id=command.segment_id,
            action="assigned",
            planning=PlanningResult.from_mapping(summary),
            technician=command.technician,
        )

    def create_allocation(
        self,
        command: ManualAllocationCreateCommand,
    ) -> AllocationMutationResult:
        identifier = self._allocations.create_manual_command(command)
        return AllocationMutationResult(identifier, action="created")

    def update_allocation(
        self,
        command: ManualAllocationUpdateCommand,
    ) -> AllocationMutationResult:
        self._allocations.update_manual_command(command)
        return AllocationMutationResult(command.allocation_id, action="updated")

    def release_allocation(
        self,
        command: ManualAllocationReleaseCommand,
    ) -> AllocationMutationResult:
        self._allocations.release_manual_command(command)
        return AllocationMutationResult(command.allocation_id, action="released")

    def delete_allocation(
        self,
        command: ManualAllocationDeleteCommand,
    ) -> AllocationMutationResult:
        self._allocations.delete_manual_command(command)
        return AllocationMutationResult(command.allocation_id, action="deleted")

    def create_quick_shift(
        self,
        command: QuickShiftCreateCommand,
    ) -> QuickShiftCreatedResult:
        result = self._quick_shifts.create_command(command)
        return QuickShiftCreatedResult(
            segment_id=result.segment_id,
            allocation_id=result.allocation_id,
        )

    def rebuild_planning(self, command: PlanningRebuildCommand) -> PlanningResult:
        return PlanningResult.from_mapping(self._planning.rebuild_command(command))
