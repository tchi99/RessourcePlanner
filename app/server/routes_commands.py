from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, Header, status

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
    IdempotentCommandExecutor,
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
    WorkPackageCreateCommand,
    WorkPackageUpdateCommand,
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
    WorkPackageCreateRequest,
    WorkPackageUpdateRequest,
)


FacadeProvider = Callable[..., Any]
IdempotencyProvider = Callable[..., Any]


def _payload(result: Any) -> dict[str, Any]:
    return result.to_dict()


def _json_body(body: Any) -> dict[str, Any]:
    return body.model_dump(mode="json")


def _segment_command_values(body: SegmentCreateRequest | SegmentUpdateRequest) -> dict[str, Any]:
    values = body.model_dump(exclude_unset=isinstance(body, SegmentUpdateRequest))
    if "source_effort_id" in values:
        values["source_effort_row"] = values.pop("source_effort_id")
    return values


def build_command_router(
    facade_dependency: FacadeProvider,
    idempotency_dependency: IdempotencyProvider,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["commands"])

    @router.post("/work-packages", status_code=status.HTTP_201_CREATED)
    def create_work_package(
        body: WorkPackageCreateRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        facade: ApplicationFacade = Depends(facade_dependency),
        idempotency: IdempotentCommandExecutor = Depends(idempotency_dependency),
    ) -> dict[str, Any]:
        return idempotency.execute(
            scope="work_package.create",
            key=idempotency_key,
            request_payload=_json_body(body),
            action=lambda: _payload(
                facade.create_work_package(WorkPackageCreateCommand(**body.model_dump()))
            ),
        )

    @router.patch("/work-packages/{reference}")
    def update_work_package(
        reference: str,
        body: WorkPackageUpdateRequest,
        facade: ApplicationFacade = Depends(facade_dependency),
    ) -> dict[str, Any]:
        return _payload(
            facade.update_work_package(
                WorkPackageUpdateCommand(
                    reference=reference,
                    **body.model_dump(exclude_unset=True),
                )
            )
        )

    @router.post("/demands", status_code=status.HTTP_201_CREATED)
    def create_demand(
        body: DemandCreateRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        facade: ApplicationFacade = Depends(facade_dependency),
        idempotency: IdempotentCommandExecutor = Depends(idempotency_dependency),
    ) -> dict[str, Any]:
        return idempotency.execute(
            scope="demand.create",
            key=idempotency_key,
            request_payload=_json_body(body),
            action=lambda: _payload(
                facade.create_demand(DemandCreateCommand(**body.model_dump()))
            ),
        )

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
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        facade: ApplicationFacade = Depends(facade_dependency),
        idempotency: IdempotentCommandExecutor = Depends(idempotency_dependency),
    ) -> dict[str, Any]:
        return idempotency.execute(
            scope="segment.create",
            key=idempotency_key,
            request_payload=_json_body(body),
            action=lambda: _payload(
                facade.create_segment(
                    SegmentCreateCommand(**_segment_command_values(body))
                )
            ),
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
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        facade: ApplicationFacade = Depends(facade_dependency),
        idempotency: IdempotentCommandExecutor = Depends(idempotency_dependency),
    ) -> dict[str, Any]:
        request_payload = {
            "segment_id": segment_id,
            "body": _json_body(body),
        }
        return idempotency.execute(
            scope="manual_allocation.create",
            key=idempotency_key,
            request_payload=request_payload,
            action=lambda: _payload(
                facade.create_allocation(
                    ManualAllocationCreateCommand(
                        segment_id=segment_id,
                        **body.model_dump(),
                    )
                )
            ),
        )

    @router.put("/allocations/{allocation_id}")
    def update_allocation(
        allocation_id: str,
        body: ManualAllocationRequest,
        facade: ApplicationFacade = Depends(facade_dependency),
    ) -> dict[str, Any]:
        values = body.model_dump()
        confirmation = values.pop("confirmation")
        return _payload(
            facade.update_allocation(
                ManualAllocationUpdateCommand(
                    allocation_id=allocation_id,
                    confirmation=confirmation,
                    clear_confirmation_override=confirmation is None,
                    **values,
                )
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
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        facade: ApplicationFacade = Depends(facade_dependency),
        idempotency: IdempotentCommandExecutor = Depends(idempotency_dependency),
    ) -> dict[str, Any]:
        return idempotency.execute(
            scope="quick_shift.create",
            key=idempotency_key,
            request_payload=_json_body(body),
            action=lambda: _payload(
                facade.create_quick_shift(
                    QuickShiftCreateCommand(**body.model_dump())
                )
            ),
        )

    @router.post("/planning/rebuild")
    def rebuild_planning(
        facade: ApplicationFacade = Depends(facade_dependency),
    ) -> dict[str, Any]:
        return _payload(facade.rebuild_planning(PlanningRebuildCommand()))

    return router
