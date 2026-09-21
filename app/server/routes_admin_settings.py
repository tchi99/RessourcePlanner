from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from ..application.security import AuthPrincipal
from ..application.smtp_settings import (
    SMTP_SECURITY_MODES,
    SmtpConfigurationService,
    SmtpConfigurationUpdate,
    SmtpConfigurationView,
)


SmtpSettingsProvider = Callable[..., Any]


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SmtpConfigurationRequest(StrictRequest):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    security: str
    username: str | None = None
    password: str | None = None
    clear_password: bool = False
    from_email: str = Field(min_length=3, max_length=320)
    from_name: str | None = Field(default=None, max_length=255)
    reply_to: str | None = Field(default=None, max_length=320)
    timeout_seconds: int = Field(ge=1, le=120)
    enabled: bool = False


def _actor(request: Request) -> str:
    principal: AuthPrincipal | None = getattr(request.state, "auth_principal", None)
    return principal.display_name if principal is not None else "api"


def build_admin_settings_router(
    smtp_dependency: SmtpSettingsProvider,
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/admin/settings",
        tags=["admin-settings"],
    )

    @router.get("/smtp")
    def get_smtp_configuration(
        service: SmtpConfigurationService = Depends(smtp_dependency),
    ) -> SmtpConfigurationView:
        return service.get()

    @router.put("/smtp")
    def update_smtp_configuration(
        body: SmtpConfigurationRequest,
        request: Request,
        service: SmtpConfigurationService = Depends(smtp_dependency),
    ) -> SmtpConfigurationView:
        security = str(body.security or "").strip().upper()
        if security not in SMTP_SECURITY_MODES:
            # Keep the application service as the canonical validator, but this
            # preserves a clean request contract for the UI/OpenAPI.
            security = body.security
        return service.update(
            SmtpConfigurationUpdate(
                host=body.host,
                port=body.port,
                security=security,
                username=body.username,
                password=body.password,
                clear_password=body.clear_password,
                from_email=body.from_email,
                from_name=body.from_name,
                reply_to=body.reply_to,
                timeout_seconds=body.timeout_seconds,
                enabled=body.enabled,
            ),
            actor_name=_actor(request),
        )

    @router.post("/smtp/test")
    def test_smtp_connection(
        service: SmtpConfigurationService = Depends(smtp_dependency),
    ) -> dict[str, object]:
        service.test_connection()
        return {
            "ok": True,
            "message": "Connexion SMTP réussie.",
        }

    return router
