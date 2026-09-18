from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ..application.dev_user_switcher import DevUserSwitcherService
from ..infrastructure.sql import SqlUserIdentityRepository
from .dev_user_switcher import (
    DevUserSwitcherRuntime,
    create_dev_user_session,
    revoke_dev_user_session,
)


class SelectDevUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1)


def build_dev_user_switcher_router(runtime: DevUserSwitcherRuntime) -> APIRouter:
    router = APIRouter(prefix="/api/v1/dev/user-switcher", tags=["dev-user-switcher"])

    @router.get("")
    def list_users(request: Request) -> dict[str, object]:
        factory = request.app.state.session_factory
        with factory() as session:
            users = DevUserSwitcherService(
                SqlUserIdentityRepository(session)
            ).list_selectable_users()
        return {
            "enabled": True,
            "bootstrap": runtime.bootstrap_principal.to_dict(),
            "users": [user.to_dict() for user in users],
        }

    @router.post("/select")
    def select_user(body: SelectDevUserRequest, request: Request) -> JSONResponse:
        factory = request.app.state.session_factory
        with factory() as session:
            principal = DevUserSwitcherService(
                SqlUserIdentityRepository(session)
            ).select_user(body.user_id)

        raw_session = create_dev_user_session(
            factory,
            runtime,
            user_id=principal.local_user_id or "",
        )
        response = JSONResponse({"principal": principal.to_dict()})
        response.set_cookie(
            runtime.cookie_name,
            raw_session,
            max_age=int(runtime.session_ttl.total_seconds()),
            httponly=True,
            secure=False,
            samesite="lax",
            path="/",
        )
        return response

    @router.post("/reset")
    def reset_user(request: Request) -> JSONResponse:
        factory = request.app.state.session_factory
        revoke_dev_user_session(factory, runtime, request)
        response = JSONResponse({"principal": runtime.bootstrap_principal.to_dict()})
        response.delete_cookie(
            runtime.cookie_name,
            path="/",
            httponly=True,
            secure=False,
            samesite="lax",
        )
        return response

    return router
