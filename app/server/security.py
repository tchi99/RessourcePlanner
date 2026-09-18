from __future__ import annotations

from collections.abc import Awaitable, Callable
import inspect
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from ..application.security import (
    AuthPrincipal,
    PERMISSION_ADMIN_USERS,
    PERMISSION_APPROVE_DEMANDS,
    PERMISSION_MANAGE_COMMUNICATIONS,
    PERMISSION_MANAGE_DEMANDS,
    PERMISSION_MANAGE_PLANNING,
    PERMISSION_MANAGE_RESOURCES,
    PERMISSION_MANAGE_WORK_PACKAGES,
    PERMISSION_READ,
    PERMISSION_SYNC_PROJECTS,
)
from .performance import performance_phase


AuthResolverResult = AuthPrincipal | None | Awaitable[AuthPrincipal | None]
AuthResolver = Callable[[Request], AuthResolverResult]

_PUBLIC_PREFIXES = ("/assets/",)
_PUBLIC_PATHS = {
    "/",
    "/health",
    "/ready",
    "/docs",
    "/docs/",
    "/openapi.json",
    "/redoc",
    "/favicon.ico",
    "/api/v1/auth/login",
    "/api/v1/auth/callback",
}


def required_permission(method: str, path: str) -> str | None:
    verb = str(method).upper()
    if not path.startswith("/api/v1/"):
        return None
    if path in {"/api/v1/auth/me", "/api/v1/auth/logout"}:
        return None
    if path.startswith("/api/v1/admin/users"):
        return PERMISSION_ADMIN_USERS
    if path.startswith("/api/v1/communications"):
        return PERMISSION_MANAGE_COMMUNICATIONS
    if verb == "GET":
        return PERMISSION_READ
    if path.startswith("/api/v1/resources") or path.startswith("/api/v1/availability-rules"):
        return PERMISSION_MANAGE_RESOURCES
    if path.startswith("/api/v1/work-packages"):
        return PERMISSION_MANAGE_WORK_PACKAGES
    if path.startswith("/api/v1/demands"):
        if (
            path.endswith("/approve")
            or path.endswith("/correction")
            or path.endswith("/emergency-plan")
        ):
            return PERMISSION_APPROVE_DEMANDS
        return PERMISSION_MANAGE_DEMANDS
    if (
        path.startswith("/api/v1/segments")
        or path.startswith("/api/v1/allocations")
        or path.startswith("/api/v1/quick-shifts")
        or path.startswith("/api/v1/planning/")
    ):
        return PERMISSION_MANAGE_PLANNING
    if path == "/api/v1/integrations/acumatica/projects/sync":
        return PERMISSION_SYNC_PROJECTS
    return "__unassigned_mutation__"


def _error(status_code: int, code: str, message: str, *, context: dict[str, Any] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "context": dict(context or {}),
            }
        },
    )


def static_auth_resolver(principal: AuthPrincipal | None) -> AuthResolver:
    def resolve(_request: Request) -> AuthPrincipal | None:
        return principal

    return resolve


async def resolve_principal(resolver: AuthResolver, request: Request) -> AuthPrincipal | None:
    resolved = resolver(request)
    if inspect.isawaitable(resolved):
        return await resolved
    return resolved


def install_authorization_middleware(app: Any, resolver: AuthResolver) -> None:
    @app.middleware("http")
    async def authorize(request: Request, call_next):
        path = request.url.path
        if path in _PUBLIC_PATHS or any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES):
            return await call_next(request)
        if not path.startswith("/api/v1/"):
            return await call_next(request)

        with performance_phase("auth"):
            principal = await resolve_principal(resolver, request)
            if principal is None:
                return _error(
                    401,
                    "authentication_required",
                    "Une authentification est requise pour accéder à RessourcePlanner.",
                )
            request.state.auth_principal = principal
            permission = required_permission(request.method, path)
            if permission is not None and not principal.has_permission(permission):
                return _error(
                    403,
                    "permission_denied",
                    "Vous n'avez pas la permission requise pour cette opération.",
                    context={"required_permission": permission},
                )
        return await call_next(request)
