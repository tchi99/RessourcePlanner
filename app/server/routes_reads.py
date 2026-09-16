from __future__ import annotations

from datetime import date
from typing import Any, Callable

from fastapi import APIRouter, Depends, Query

from ..application import (
    ApplicationNotFoundError,
    ApplicationValidationError,
    DemandHistoryReadModel,
    DemandPeriodReadModel,
    DemandReadModel,
    PlannerQueryPort,
    PlanningSnapshotReadModel,
    ProjectReadModel,
    ResourceAvailabilityRuleReadModel,
    ResourceReadModel,
    SegmentReadModel,
    ShiftReadModel,
    WorkPackageReadModel,
)


QueryProvider = Callable[..., Any]


def _window(start: date | None, end: date | None) -> None:
    if start is not None and end is not None and end < start:
        raise ApplicationValidationError(
            "La date de fin ne peut pas précéder la date de début.",
            code="query_date_window_invalid",
            context={"start": start.isoformat(), "end": end.isoformat()},
        )


def build_read_router(query_dependency: QueryProvider) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["reads"])

    @router.get("/projects")
    def list_projects(
        active_only: bool = False,
        queries: PlannerQueryPort = Depends(query_dependency),
    ) -> list[ProjectReadModel]:
        return list(queries.list_projects(active_only=active_only))

    @router.get("/work-packages")
    def list_work_packages(
        project_number: str | None = Query(default=None),
        active_only: bool = True,
        queries: PlannerQueryPort = Depends(query_dependency),
    ) -> list[WorkPackageReadModel]:
        return list(
            queries.list_work_packages(
                project_number=project_number,
                active_only=active_only,
            )
        )

    @router.get("/resources")
    def list_resources(
        active_only: bool = True,
        queries: PlannerQueryPort = Depends(query_dependency),
    ) -> list[ResourceReadModel]:
        return list(queries.list_resources(active_only=active_only))

    @router.get("/availability-rules")
    def list_availability_rules(
        resource_id: str | None = Query(default=None),
        include_global: bool = True,
        active_only: bool = True,
        queries: PlannerQueryPort = Depends(query_dependency),
    ) -> list[ResourceAvailabilityRuleReadModel]:
        return list(
            queries.list_availability_rules(
                resource_id=resource_id,
                include_global=include_global,
                active_only=active_only,
            )
        )

    @router.get("/demands")
    def list_demands(
        queries: PlannerQueryPort = Depends(query_dependency),
    ) -> list[DemandReadModel]:
        return list(queries.list_demands())

    @router.get("/demands/{number}")
    def get_demand(
        number: str,
        queries: PlannerQueryPort = Depends(query_dependency),
    ) -> DemandReadModel:
        row = queries.get_demand(number)
        if row is None:
            raise ApplicationNotFoundError(
                f"Demande {number} introuvable",
                code="demand_not_found",
                context={"demand_number": number},
            )
        return row

    @router.get("/demands/{number}/history")
    def list_demand_history(
        number: str,
        queries: PlannerQueryPort = Depends(query_dependency),
    ) -> list[DemandHistoryReadModel]:
        if queries.get_demand(number) is None:
            raise ApplicationNotFoundError(
                f"Demande {number} introuvable",
                code="demand_not_found",
                context={"demand_number": number},
            )
        return list(queries.list_demand_history(number))

    @router.get("/demands/{number}/periods")
    def list_demand_periods(
        number: str,
        queries: PlannerQueryPort = Depends(query_dependency),
    ) -> list[DemandPeriodReadModel]:
        if queries.get_demand(number) is None:
            raise ApplicationNotFoundError(
                f"Demande {number} introuvable",
                code="demand_not_found",
                context={"demand_number": number},
            )
        return list(queries.list_demand_periods(number))

    @router.get("/segments")
    def list_segments(
        start: date | None = Query(default=None),
        end: date | None = Query(default=None),
        include_cancelled: bool = False,
        queries: PlannerQueryPort = Depends(query_dependency),
    ) -> list[SegmentReadModel]:
        _window(start, end)
        return list(
            queries.list_segments(start=start, end=end, include_cancelled=include_cancelled)
        )

    @router.get("/segments/{segment_id}")
    def get_segment(
        segment_id: str,
        queries: PlannerQueryPort = Depends(query_dependency),
    ) -> SegmentReadModel:
        row = queries.get_segment(segment_id)
        if row is None:
            raise ApplicationNotFoundError(
                f"Segment {segment_id} introuvable",
                code="segment_not_found",
                context={"segment_id": segment_id},
            )
        return row

    @router.get("/shifts")
    def list_shifts(
        start: date | None = Query(default=None),
        end: date | None = Query(default=None),
        resource_name: str | None = Query(default=None),
        queries: PlannerQueryPort = Depends(query_dependency),
    ) -> list[ShiftReadModel]:
        _window(start, end)
        return list(
            queries.list_shifts(start=start, end=end, resource_name=resource_name)
        )

    @router.get("/planning/snapshot")
    def planning_snapshot(
        start: date = Query(),
        end: date = Query(),
        queries: PlannerQueryPort = Depends(query_dependency),
    ) -> PlanningSnapshotReadModel:
        _window(start, end)
        return queries.planning_snapshot(start=start, end=end)

    return router
