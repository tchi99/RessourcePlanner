from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Any, Callable

from fastapi import APIRouter, Depends, Query

from ..application import (
    ApplicationNotFoundError,
    ApplicationValidationError,
    PlannerQueryPort,
)


QueryProvider = Callable[..., Any]


def _dict(value: object) -> dict[str, Any]:
    return asdict(value)  # type: ignore[arg-type]


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
    ) -> list[dict[str, Any]]:
        return [
            _dict(row)
            for row in queries.list_projects(active_only=active_only)
        ]

    @router.get("/resources")
    def list_resources(
        active_only: bool = True,
        queries: PlannerQueryPort = Depends(query_dependency),
    ) -> list[dict[str, Any]]:
        return [
            _dict(row)
            for row in queries.list_resources(active_only=active_only)
        ]

    @router.get("/demands")
    def list_demands(
        queries: PlannerQueryPort = Depends(query_dependency),
    ) -> list[dict[str, Any]]:
        return [_dict(row) for row in queries.list_demands()]

    @router.get("/demands/{number}")
    def get_demand(
        number: str,
        queries: PlannerQueryPort = Depends(query_dependency),
    ) -> dict[str, Any]:
        row = queries.get_demand(number)
        if row is None:
            raise ApplicationNotFoundError(
                f"Demande {number} introuvable",
                code="demand_not_found",
                context={"demand_number": number},
            )
        return _dict(row)

    @router.get("/segments")
    def list_segments(
        start: date | None = Query(default=None),
        end: date | None = Query(default=None),
        include_cancelled: bool = False,
        queries: PlannerQueryPort = Depends(query_dependency),
    ) -> list[dict[str, Any]]:
        _window(start, end)
        return [
            _dict(row)
            for row in queries.list_segments(
                start=start,
                end=end,
                include_cancelled=include_cancelled,
            )
        ]

    @router.get("/segments/{segment_id}")
    def get_segment(
        segment_id: str,
        queries: PlannerQueryPort = Depends(query_dependency),
    ) -> dict[str, Any]:
        row = queries.get_segment(segment_id)
        if row is None:
            raise ApplicationNotFoundError(
                f"Segment {segment_id} introuvable",
                code="segment_not_found",
                context={"segment_id": segment_id},
            )
        return _dict(row)

    @router.get("/shifts")
    def list_shifts(
        start: date | None = Query(default=None),
        end: date | None = Query(default=None),
        resource_name: str | None = Query(default=None),
        queries: PlannerQueryPort = Depends(query_dependency),
    ) -> list[dict[str, Any]]:
        _window(start, end)
        return [
            _dict(row)
            for row in queries.list_shifts(
                start=start,
                end=end,
                resource_name=resource_name,
            )
        ]

    return router
