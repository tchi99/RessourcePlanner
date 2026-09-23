"""Explicit API for the physical asset catalogue and reservation commands."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
import json
from typing import Callable

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..infrastructure.sql.asset_models import Asset, AssetAllocation, AssetRequirement, AssetType, AssetUnavailability
from ..infrastructure.sql.asset_service import SqlAssetService
from ..infrastructure.sql.planning_version import SqlPlanningMutationVersionRepository


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TypeCreate(StrictBody):
    code: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=255)
    category: str
    metadata: dict | None = None


class AssetCreate(StrictBody):
    code: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=255)
    asset_type_id: str
    metadata: dict | None = None


class ActiveUpdate(StrictBody):
    active: bool
    expected_planning_version: int = Field(ge=1)


class TypeUpdate(StrictBody):
    expected_planning_version: int = Field(ge=1)
    code: str | None = None
    label: str | None = None
    category: str | None = None
    active: bool | None = None
    metadata: dict | None = None


class AssetUpdate(StrictBody):
    expected_planning_version: int = Field(ge=1)
    code: str | None = None
    label: str | None = None
    asset_type_id: str | None = None
    active: bool | None = None
    metadata: dict | None = None


class UnavailabilityCreate(StrictBody):
    start_date: date
    end_date: date
    reason: str | None = None
    expected_planning_version: int = Field(ge=1)


class ReservationChange(StrictBody):
    asset_id: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    expected_planning_version: int = Field(ge=1)


def build_asset_router(session_dependency: Callable[[], Iterator[Session]]) -> APIRouter:
    router = APIRouter(prefix="/api/v1/assets", tags=["assets"])

    def service(session: Session, request: Request) -> SqlAssetService:
        principal = getattr(request.state, "auth_principal", None)
        actor = str(getattr(principal, "local_user_id", None) or "api")
        return SqlAssetService(session, actor=actor)

    @router.get("/catalog")
    def catalog(session: Session = Depends(session_dependency)) -> dict:
        return {
            "types": [{"id": row.id, "code": row.code, "label": row.label, "category": row.category,
                       "active": row.active, "occupancy_policy": row.occupancy_policy,
                       "metadata": json.loads(row.metadata_json or "{}")}
                      for row in session.scalars(select(AssetType).order_by(AssetType.code))],
            "assets": [{"id": row.id, "code": row.code, "label": row.label, "asset_type_id": row.asset_type_id,
                        "active": row.active, "metadata": json.loads(row.metadata_json or "{}")}
                       for row in session.scalars(select(Asset).order_by(Asset.code))],
            "planning_version": SqlPlanningMutationVersionRepository(session).current_version(),
        }

    @router.post("/types", status_code=201)
    def create_type(body: TypeCreate, request: Request, session: Session = Depends(session_dependency)) -> dict:
        row = service(session, request).create_type(**body.model_dump())
        return {"id": row.id, "code": row.code}

    @router.post("", status_code=201)
    def create_asset(body: AssetCreate, request: Request, session: Session = Depends(session_dependency)) -> dict:
        row = service(session, request).create_asset(**body.model_dump())
        return {"id": row.id, "code": row.code}

    @router.patch("/types/{identifier}/active")
    def activate_type(identifier: str, body: ActiveUpdate, request: Request, session: Session = Depends(session_dependency)) -> dict:
        return service(session, request).set_active(AssetType, identifier, body.active, body.expected_planning_version)

    @router.patch("/types/{identifier}")
    def update_type(identifier: str, body: TypeUpdate, request: Request, session: Session = Depends(session_dependency)) -> dict:
        return service(session, request).update_catalog(AssetType, identifier,
            body.model_dump(exclude_unset=True, exclude={"expected_planning_version"}), body.expected_planning_version)

    @router.patch("/{identifier}/active")
    def activate_asset(identifier: str, body: ActiveUpdate, request: Request, session: Session = Depends(session_dependency)) -> dict:
        return service(session, request).set_active(Asset, identifier, body.active, body.expected_planning_version)

    @router.patch("/{identifier}")
    def update_asset(identifier: str, body: AssetUpdate, request: Request, session: Session = Depends(session_dependency)) -> dict:
        return service(session, request).update_catalog(Asset, identifier,
            body.model_dump(exclude_unset=True, exclude={"expected_planning_version"}), body.expected_planning_version)

    @router.post("/{identifier}/unavailability", status_code=201)
    def add_unavailability(identifier: str, body: UnavailabilityCreate, request: Request,
                           session: Session = Depends(session_dependency)) -> dict:
        return service(session, request).add_unavailability(asset_id=identifier, **body.model_dump(exclude={"expected_planning_version"}),
                                                            expected_version=body.expected_planning_version)

    @router.delete("/{identifier}/unavailability/{unavailability_id}")
    def remove_unavailability(identifier: str, unavailability_id: str, expected_planning_version: int,
                              request: Request, session: Session = Depends(session_dependency)) -> dict:
        return service(session, request).remove_unavailability(
            asset_id=identifier, identifier=unavailability_id, expected_version=expected_planning_version)

    @router.get("/requirements")
    def requirements(session: Session = Depends(session_dependency)) -> dict:
        return {
            "requirements": [{"id": row.id, "request_id": row.workforce_request_id, "asset_type_id": row.asset_type_id,
                              "start_date": row.start_date, "end_date": row.end_date, "usage_hours": row.usage_hours,
                              "status": row.status, "approved_entry_key": row.approved_entry_key}
                             for row in session.scalars(select(AssetRequirement))],
            "allocations": [{"id": row.id, "requirement_id": row.asset_requirement_id, "asset_id": row.asset_id,
                             "start_date": row.start_date, "end_date": row.end_date, "locked": row.locked}
                            for row in session.scalars(select(AssetAllocation))],
            "unavailability": [{"id": row.id, "asset_id": row.asset_id, "start_date": row.start_date,
                                "end_date": row.end_date, "reason": row.reason}
                               for row in session.scalars(select(AssetUnavailability))],
            "planning_version": SqlPlanningMutationVersionRepository(session).current_version(),
        }

    @router.put("/requirements/{identifier}/reservation")
    def reserve(identifier: str, body: ReservationChange, request: Request,
                idempotency_key: str = Header(alias="Idempotency-Key", min_length=1),
                session: Session = Depends(session_dependency)) -> dict:
        return service(session, request).reserve(requirement_id=identifier, asset_id=body.asset_id,
                                                 start_date=body.start_date, end_date=body.end_date,
                                                 expected_version=body.expected_planning_version,
                                                 idempotency_key=idempotency_key)

    return router
