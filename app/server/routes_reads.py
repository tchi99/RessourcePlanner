from __future__ import annotations

from datetime import date
from typing import Any, Callable, Literal

from fastapi import APIRouter, Depends, Query, Request

from ..application import (
    ApplicationConflictError,
    ApplicationNotFoundError,
    ApplicationValidationError,
    DemandApprovalStateReadModel,
    DemandDetailReadModel,
    DemandDetailService,
    DemandHistoryReadModel,
    DemandPeriodReadModel,
    DemandPlanDeltaReadModel,
    DemandReadModel,
    DemandRequesterReadModel,
    DemandRequesterService,
    MediumTermUnlinkedSegmentReadModel,
    OperationalContactService,
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


def _planning_scope_context(
    request: Request,
    scope: ViewScope,
    repository: UserViewContextRepositoryPort | None,
) -> tuple[tuple[str, ...] | None, tuple[str, ...]]:
    if repository is None:
        return None, ()
    principal: AuthPrincipal = request.state.auth_principal
    service = UserViewContextService(repository)
    resolution = service.resolve_project_scope(principal, scope)
    if resolution.project_ids is None:
        return None, ()
    relations = service.resolve_relations(principal)
    personal_resource_ids = (
        (relations.resource.id,)
        if relations.resource is not None
        else ()
    )
    return resolution.project_ids, personal_resource_ids


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
    demand_requester_dependency: QueryProvider | None = None,
    operational_contact_dependency: QueryProvider | None = None,
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

    if demand_requester_dependency is not None:

        @router.get("/demand-requesters")
        def list_demand_requesters(
            service: DemandRequesterService = Depends(demand_requester_dependency),
        ) -> list[DemandRequesterReadModel]:
            return list(service.list_admissible())

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

    if operational_contact_dependency is not None:

        @router.get("/demands/{number}/detail")
        def get_demand_detail(
            number: str,
            request: Request,
            queries: PlannerQueryPort = Depends(query_dependency),
            contacts: OperationalContactService = Depends(
                operational_contact_dependency
            ),
        ) -> DemandDetailReadModel:
            principal: AuthPrincipal = request.state.auth_principal
            return DemandDetailService(queries, contacts).get(
                number,
                permissions=principal.permissions,
            )

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
        demand = queries.get_demand(number)
        if demand is None:
            raise ApplicationNotFoundError(
                f"Demande {number} introuvable",
                code="demand_not_found",
                context={"demand_number": number},
            )
        if demand.line_mode:
            raise ApplicationConflictError(
                "Les périodes d'une demande multi-lignes doivent être lues par ligne.",
                code="demand_line_period_scope_required",
                context={"demand_number": number},
            )
        return list(queries.list_demand_periods(number))

    @router.get("/demands/{number}/lines/{line_id}/periods")
    def list_demand_line_periods(
        number: str,
        line_id: str,
        queries: PlannerQueryPort = Depends(query_dependency),
    ) -> list[DemandPeriodReadModel]:
        demand = queries.get_demand(number)
        if demand is None:
            raise ApplicationNotFoundError(
                f"Demande {number} introuvable",
                code="demand_not_found",
                context={"demand_number": number},
            )
        if not demand.line_mode:
            raise ApplicationConflictError(
                "Les demandes historiques à une ligne utilisent l'endpoint de périodes de la demande.",
                code="demand_legacy_period_scope_invalid",
                context={"demand_number": number},
            )
        if not any(row.active and row.line_id == line_id for row in demand.lines):
            raise ApplicationNotFoundError(
                f"Ligne {line_id} introuvable pour la demande {number}",
                code="demand_line_not_found",
                context={"demand_number": number, "request_line_id": line_id},
            )
        return list(
            queries.list_demand_periods(
                number,
                request_line_id=line_id,
            )
        )

    @router.get("/demands/{number}/approval-state")
    def demand_approval_state(
        number: str,
        queries: PlannerQueryPort = Depends(query_dependency),
    ) -> DemandApprovalStateReadModel:
        row = queries.demand_approval_state(number)
        if row is None:
            raise ApplicationNotFoundError(
                f"Demande {number} introuvable",
                code="demand_not_found",
                context={"demand_number": number},
            )
        return row

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
        request: Request,
        start: date | None = Query(default=None),
        end: date | None = Query(default=None),
        include_cancelled: bool = False,
        scope: ViewScope = Query(default=SCOPE_GLOBAL),
        queries: PlannerQueryPort = Depends(query_dependency),
        context_repository: Any = Depends(context_dependency),
    ) -> list[SegmentReadModel]:
        _window(start, end)
        project_ids = _project_ids_for_scope(request, scope, context_repository)
        if project_ids is None:
            return list(
                queries.list_segments(
                    start=start,
                    end=end,
                    include_cancelled=include_cancelled,
                )
            )
        return list(
            queries.list_segments(
                start=start,
                end=end,
                include_cancelled=include_cancelled,
                project_ids=project_ids,
            )
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
        request: Request,
        start: date | None = Query(default=None),
        end: date | None = Query(default=None),
        resource_name: str | None = Query(default=None),
        scope: ViewScope = Query(default=SCOPE_GLOBAL),
        queries: PlannerQueryPort = Depends(query_dependency),
        context_repository: Any = Depends(context_dependency),
    ) -> list[ShiftReadModel]:
        _window(start, end)
        project_ids = _project_ids_for_scope(request, scope, context_repository)
        if project_ids is None:
            return list(
                queries.list_shifts(
                    start=start,
                    end=end,
                    resource_name=resource_name,
                )
            )
        return list(
            queries.list_shifts(
                start=start,
                end=end,
                resource_name=resource_name,
                project_ids=project_ids,
            )
        )

    @router.get("/shifts/{allocation_id}/history")
    def list_shift_history(
        allocation_id: str,
        queries: PlannerQueryPort = Depends(query_dependency),
    ) -> list[PlanningHistoryReadModel]:
        return list(queries.list_planning_history("SHIFT", allocation_id))

    @router.get("/medium-term/unlinked-segments")
    def medium_term_unlinked_segments(
        request: Request,
        start: date = Query(),
        end: date = Query(),
        scope: ViewScope = Query(default=SCOPE_GLOBAL),
        queries: PlannerQueryPort = Depends(query_dependency),
        context_repository: Any = Depends(context_dependency),
    ) -> list[MediumTermUnlinkedSegmentReadModel]:
        _window(start, end)
        project_ids = _project_ids_for_scope(request, scope, context_repository)
        if project_ids is None:
            return list(
                queries.list_medium_term_unlinked_segments(
                    start=start,
                    end=end,
                )
            )
        return list(
            queries.list_medium_term_unlinked_segments(
                start=start,
                end=end,
                project_ids=project_ids,
            )
        )

    @router.get("/planning/capacity-grid")
    def planning_capacity_grid(
        request: Request,
        start: date = Query(),
        end: date = Query(),
        scope: ViewScope = Query(default=SCOPE_GLOBAL),
        queries: PlannerQueryPort = Depends(query_dependency),
        context_repository: Any = Depends(context_dependency),
    ) -> PlanningCapacityGridReadModel:
        _window(start, end)
        project_ids, personal_resource_ids = _planning_scope_context(
            request,
            scope,
            context_repository,
        )
        if project_ids is None:
            return queries.planning_capacity_grid(start=start, end=end)
        return queries.planning_capacity_grid(
            start=start,
            end=end,
            project_ids=project_ids,
            include_resource_ids=personal_resource_ids,
        )

    @router.get("/planning/actions")
    def planning_actions(
        request: Request,
        start: date = Query(),
        end: date = Query(),
        scope: ViewScope = Query(default=SCOPE_GLOBAL),
        queries: PlannerQueryPort = Depends(query_dependency),
        context_repository: Any = Depends(context_dependency),
    ) -> list[PlanningActionReadModel]:
        _window(start, end)
        project_ids = _project_ids_for_scope(request, scope, context_repository)
        if project_ids is None:
            return list(queries.list_planning_actions(start=start, end=end))
        return list(
            queries.list_planning_actions(
                start=start,
                end=end,
                project_ids=project_ids,
            )
        )

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
        request: Request,
        start: date = Query(),
        end: date = Query(),
        scope: ViewScope = Query(default=SCOPE_GLOBAL),
        queries: PlannerQueryPort = Depends(query_dependency),
        context_repository: Any = Depends(context_dependency),
    ) -> PlanningSnapshotReadModel:
        _window(start, end)
        project_ids, personal_resource_ids = _planning_scope_context(
            request,
            scope,
            context_repository,
        )
        if project_ids is None:
            return queries.planning_snapshot(start=start, end=end)
        return queries.planning_snapshot(
            start=start,
            end=end,
            project_ids=project_ids,
            include_resource_ids=personal_resource_ids,
        )

    return router
