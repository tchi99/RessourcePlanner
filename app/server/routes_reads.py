from __future__ import annotations

from datetime import date
from typing import Any, Callable, Literal

from fastapi import APIRouter, Depends, Query, Request

from ..application import (
    ApplicationNotFoundError,
    ApplicationValidationError,
    DemandHistoryReadModel,
    DemandPeriodReadModel,
    DemandPlanDeltaReadModel,
    DemandReadModel,
    MediumTermUnlinkedSegmentReadModel,
    PlannerQueryPort,
    PlanningActionReadModel,
    PlanningCapacityGridReadModel,
    PlanningSnapshotReadModel,
    ProjectReadModel,
    ResourceAvailabilityRuleReadModel,
    ResourceReadModel,
    ResourceRecommendationReadModel,
    SegmentReadModel,
    ShiftReadModel,
    WorkPackageReadModel,
)
from ..application.query_models import PlanningHistoryReadModel
from ..application.security import AuthPrincipal
from ..application.user_view_context import (
    SCOPE_GLOBAL,
    SCOPE_MINE,
    UserViewContextRepositoryPort,
    UserViewContextService,
)


QueryProvider = Callable[..., Any]
ViewScope = Literal["mine", "global"]


def _project_ids_for_scope(
    request: Request,
    scope: ViewScope,
    repository: UserViewContextRepositoryPort | None,
) -> tuple[str, ...] | None:
    if repository is None:
        return None
    principal: AuthPrincipal = request.state.auth_principal
    return UserViewContextService(repository).resolve_project_scope(
        principal,
        scope,
    ).project_ids


def _window(start: date | None, end: date | None) -> None:
    if start is not None and end is not None and end < start:
        raise ApplicationValidationError(
            "La date de fin ne peut pas précéder la date de début.",
            code="query_date_window_invalid",
            context={"start": start.isoformat(), "end": end.isoformat()},
        )


def build_read_router(
    query_dependency: QueryProvider,
    user_view_context_dependency: QueryProvider | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["reads"])

    def no_context_repository() -> None:
        return None

    context_dependency = user_view_context_dependency or no_context_repository

    @router.get("/projects")
    def list_projects(
        request: Request,
        active_only: bool = False,
        scope: ViewScope = Query(default=SCOPE_GLOBAL),
        queries: PlannerQueryPort = Depends(query_dependency),
        context_repository: Any = Depends(context_dependency),
    ) -> list[ProjectReadModel]:
        project_ids = _project_ids_for_scope(request, scope, context_repository)
        if project_ids is None:
            return list(queries.list_projects(active_only=active_only))
        return list(
            queries.list_projects(
                active_only=active_only,
                project_ids=project_ids,
            )
        )

    @router.get("/work-packages")
    def list_work_packages(
        request: Request,
        project_number: str | None = Query(default=None),
        active_only: bool = True,
        scope: ViewScope = Query(default=SCOPE_GLOBAL),
        queries: PlannerQueryPort = Depends(query_dependency),
        context_repository: Any = Depends(context_dependency),
    ) -> list[WorkPackageReadModel]:
        project_ids = _project_ids_for_scope(request, scope, context_repository)
        if project_ids is None:
            return list(
                queries.list_work_packages(
                    project_number=project_number,
                    active_only=active_only,
                )
            )
        return list(
            queries.list_work_packages(
                project_number=project_number,
                active_only=active_only,
                project_ids=project_ids,
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
        request: Request,
        scope: ViewScope = Query(default=SCOPE_GLOBAL),
        queries: PlannerQueryPort = Depends(query_dependency),
        context_repository: Any = Depends(context_dependency),
    ) -> list[DemandReadModel]:
        project_ids = _project_ids_for_scope(request, scope, context_repository)
        if project_ids is None:
            return list(queries.list_demands())
        return list(queries.list_demands(project_ids=project_ids))

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

    @router.get("/demands/{number}/plan-delta")
    def demand_plan_delta(
        number: str,
        queries: PlannerQueryPort = Depends(query_dependency),
    ) -> DemandPlanDeltaReadModel:
        row = queries.demand_plan_delta(number)
        if row is None:
            raise ApplicationNotFoundError(
                f"Demande {number} introuvable",
                code="demand_not_found",
                context={"demand_number": number},
            )
        return row

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

    @router.get("/segments/{segment_id}/history")
    def list_segment_history(
        segment_id: str,
        queries: PlannerQueryPort = Depends(query_dependency),
    ) -> list[PlanningHistoryReadModel]:
        if queries.get_segment(segment_id) is None:
            raise ApplicationNotFoundError(
                f"Segment {segment_id} introuvable",
                code="segment_not_found",
                context={"segment_id": segment_id},
            )
        return list(queries.list_planning_history("SEGMENT", segment_id))

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

    @router.get("/shifts/{allocation_id}/history")
    def list_shift_history(
        allocation_id: str,
        queries: PlannerQueryPort = Depends(query_dependency),
    ) -> list[PlanningHistoryReadModel]:
        return list(queries.list_planning_history("SHIFT", allocation_id))

    @router.get("/medium-term/unlinked-segments")
    def medium_term_unlinked_segments(
        start: date = Query(),
        end: date = Query(),
        queries: PlannerQueryPort = Depends(query_dependency),
    ) -> list[MediumTermUnlinkedSegmentReadModel]:
        _window(start, end)
        return list(queries.list_medium_term_unlinked_segments(start=start, end=end))

    @router.get("/planning/capacity-grid")
    def planning_capacity_grid(
        start: date = Query(),
        end: date = Query(),
        queries: PlannerQueryPort = Depends(query_dependency),
    ) -> PlanningCapacityGridReadModel:
        _window(start, end)
        return queries.planning_capacity_grid(start=start, end=end)

    @router.get("/planning/actions")
    def planning_actions(
        start: date = Query(),
        end: date = Query(),
        queries: PlannerQueryPort = Depends(query_dependency),
    ) -> list[PlanningActionReadModel]:
        _window(start, end)
        return list(queries.list_planning_actions(start=start, end=end))

    @router.get("/segments/{segment_id}/resource-recommendations")
    def resource_recommendations(
        segment_id: str,
        queries: PlannerQueryPort = Depends(query_dependency),
    ) -> list[ResourceRecommendationReadModel]:
        if queries.get_segment(segment_id) is None:
            raise ApplicationNotFoundError(
                f"Segment {segment_id} introuvable",
                code="segment_not_found",
                context={"segment_id": segment_id},
            )
        return list(queries.recommend_resources(segment_id))

    @router.get("/planning/snapshot")
    def planning_snapshot(
        start: date = Query(),
        end: date = Query(),
        queries: PlannerQueryPort = Depends(query_dependency),
    ) -> PlanningSnapshotReadModel:
        _window(start, end)
        return queries.planning_snapshot(start=start, end=end)

    return router
