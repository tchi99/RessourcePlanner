from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from ..application.security import AuthPrincipal


def build_auth_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

    @router.get("/me")
    def current_user(request: Request) -> dict[str, Any]:
        principal: AuthPrincipal = request.state.auth_principal
        return principal.to_dict()

    return router
