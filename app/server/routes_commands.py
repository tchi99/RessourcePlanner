from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, status

from ..application import (
    ApplicationFacade,
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
from .schemas import (
    DemandAlternativeSelectionRequest,
    DemandCreateRequest,
    DemandPeriodsReplaceRequest,
    DemandUpdateRequest,
    ManualAllocationRequest,
    OptionalCommentRequest,
    QuickShiftRequest,
    RequiredCommentRequest,
    SegmentAssignRequest,
    SegmentCreateRequest,
    SegmentUpdateRequest,
)


FacadeProvider = Callable[..., Any]


def _payload(result: Any) -> dict[str, Any]:
    return result.to_dict()


def _segment_command_values(body: SegmentCreateRequest | SegmentUpdateRequest) -> dict[str, Any]:
    values = body.model_dump(exclude_unset=isinstance(body, SegmentUpdateRequest))
    if "source_effort_id" in values:
        values["source_effort_row"] = values.pop("source_effort_id")
    return values


def build_command_router(facade_dependency: FacadeProvider) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["commands"])

    @router.post("/demands", status_code=status.HTTP_201_CREATED)
    def create_demand(
        body: DemandCreateRequest,
        facade: ApplicationFacade = Depends(facade_dependency),
    ) -> dict[str, Any]:
        return _payload(facade.create_demand(DemandCreateCommand(**body.model_dump())))

    @router.patch("/demands/{number}")
    def update_demand(
        number: str,
        body: DemandUpdateRequest,
        facade: ApplicationFacade = Depends(facade_dependency),
    ) -> dict[str, Any]:
        values = body.model_dump(exclude_unset=True)
        comment = str(values.pop("comment", "Demande modifiée via API") or "")
        command = DemandUpdateCommand(number=number, comment=comment, **values)
        return _payload(facade.update_demand(command))

    @router.put("/demands/{number}/periods")
    def replace_demand_periods(
        number: str,
        body: DemandPeriodsReplaceRequest,
        facade: ApplicationFacade = Depends(facade_dependency),
    ) -> dict[str, Any]:
        command = DemandPeriodsReplaceCommand(
            number=number,
            periods=tuple(DemandPeriodInput(**period.model_dump()) for period in body.periods),
        )
        return _payload(facade.replace_demand_periods(command))

    @router.put("/demands/{number}/alternative-groups/{alternative_group}/selection")
    def select_demand_alternative(
        number: str,
        alternative_group: str,
        body: DemandAlternativeSelectionRequest,
        facade: ApplicationFacade = Depends(facade_dependency),
    ) -> dict[str, Any]:
        return _payload(
            facade.select_demand_alternative(
                DemandAlternativeSelectCommand(
                    number=number,
                    alternative_group=alternative_group,
                    period_id=body.period_id,
                )
            )
        )

    @router.post("/demands/{number}/submit")
    def submit_demand(
        number: str,
        facade: ApplicationFacade = Depends(facade_dependency),
    ) -> dict[str, Any]:
        return _payload(facade.submit_demand(DemandSubmitCommand(number)))

    @router.post("/demands/{number}/approve")
    def approve_demand(
        number: str,
        body: OptionalCommentRequest,
        facade: ApplicationFacade = Depends(facade_dependency),
    ) -> dict[str, Any]:
        return _payload(facade.approve_demand(DemandApproveCommand(number, body.comment)))

    @router.post("/demands/{number}/correction")
    def request_demand_correction(
        number: str,
        body: RequiredCommentRequest,
        facade: ApplicationFacade = Depends(facade_dependency),
    ) -> dict[str, Any]:
        return _payload(
            facade.request_demand_correction(DemandCorrectionCommand(number, body.comment))
        )

    @router.post("/demands/{number}/cancel")
    def cancel_demand(
        number: str,
        facade: ApplicationFacade = Depends(facade_dependency),
    ) -> dict[str, Any]:
        return _payload(facade.cancel_demand(DemandCancelCommand(number)))

    @router.post("/segments", status_code=status.HTTP_201_CREATED)
    def create_segment(
        body: SegmentCreateRequest,
        facade: ApplicationFacade = Depends(facade_dependency),
    ) -> dict[str, Any]:
        return _payload(
            facade.create_segment(SegmentCreateCommand(**_segment_command_values(body)))
        )

    @router.patch("/segments/{segment_id}")
    def update_segment(
        segment_id: str,
        body: SegmentUpdateRequest,
        facade: ApplicationFacade = Depends(facade_dependency),
    ) -> dict[str, Any]:
        return _payload(
            facade.update_segment(
                SegmentUpdateCommand(segment_id=segment_id, **_segment_command_values(body))
            )
        )

    @router.post("/segments/{segment_id}/cancel")
    def cancel_segment(
        segment_id: str,
        facade: ApplicationFacade = Depends(facade_dependency),
    ) -> dict[str, Any]:
        return _payload(facade.cancel_segment(SegmentCancelCommand(segment_id)))

    @router.post("/segments/{segment_id}/assign")
    def assign_segment(
        segment_id: str,
        body: SegmentAssignRequest,
        facade: ApplicationFacade = Depends(facade_dependency),
    ) -> dict[str, Any]:
        return _payload(facade.assign_segment(SegmentAssignCommand(segment_id, body.technician)))

    @router.post("/segments/{segment_id}/allocations", status_code=status.HTTP_201_CREATED)
    def create_allocation(
        segment_id: str,
        body: ManualAllocationRequest,
        facade: ApplicationFacade = Depends(facade_dependency),
    ) -> dict[str, Any]:
        return _payload(
            facade.create_allocation(
                ManualAllocationCreateCommand(segment_id=segment_id, **body.model_dump())
            )
        )

    @router.put("/allocations/{allocation_id}")
    def update_allocation(
        allocation_id: str,
        body: ManualAllocationRequest,
        facade: ApplicationFacade = Depends(facade_dependency),
    ) -> dict[str, Any]:
        return _payload(
            facade.update_allocation(
                ManualAllocationUpdateCommand(allocation_id=allocation_id, **body.model_dump())
            )
        )

    @router.post("/allocations/{allocation_id}/release")
    def release_allocation(
        allocation_id: str,
        facade: ApplicationFacade = Depends(facade_dependency),
    ) -> dict[str, Any]:
        return _payload(facade.release_allocation(ManualAllocationReleaseCommand(allocation_id)))

    @router.delete("/allocations/{allocation_id}")
    def delete_allocation(
        allocation_id: str,
        facade: ApplicationFacade = Depends(facade_dependency),
    ) -> dict[str, Any]:
        return _payload(facade.delete_allocation(ManualAllocationDeleteCommand(allocation_id)))

    @router.post("/quick-shifts", status_code=status.HTTP_201_CREATED)
    def create_quick_shift(
        body: QuickShiftRequest,
        facade: ApplicationFacade = Depends(facade_dependency),
    ) -> dict[str, Any]:
        return _payload(facade.create_quick_shift(QuickShiftCreateCommand(**body.model_dump())))

    @router.post("/planning/rebuild")
    def rebuild_planning(
        facade: ApplicationFacade = Depends(facade_dependency),
    ) -> dict[str, Any]:
        return _payload(facade.rebuild_planning(PlanningRebuildCommand()))

    return router
