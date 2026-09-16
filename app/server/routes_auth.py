from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
import httpx

from ..application.security import AuthPrincipal, IdentityService
from ..infrastructure.acumatica.oidc import OidcProtocolError
from ..infrastructure.sql import SqlUserIdentityRepository
from .oidc import (
    OidcRuntime,
    consume_login_transaction,
    create_login_transaction,
    create_server_session,
    revoke_server_session,
)


def _auth_error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "context": {}}},
    )


def build_auth_router(oidc_runtime: OidcRuntime | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

    @router.get("/me")
    def current_user(request: Request) -> dict[str, Any]:
        principal: AuthPrincipal = request.state.auth_principal
        return principal.to_dict()

    if oidc_runtime is None:
        return router

    @router.get("/login")
    async def login(request: Request) -> Response:
        factory = request.app.state.session_factory
        state, nonce, code_verifier = create_login_transaction(factory, oidc_runtime)
        try:
            target = await oidc_runtime.client.authorization_url(
                state=state,
                nonce=nonce,
                code_verifier=code_verifier,
            )
        except (httpx.HTTPError, OidcProtocolError):
            return _auth_error(
                503,
                "oidc_provider_unavailable",
                "Le fournisseur OIDC n'est pas disponible ou sa configuration est invalide.",
            )
        return RedirectResponse(target, status_code=302)

    @router.get("/callback")
    async def callback(
        request: Request,
        code: str | None = None,
        state: str | None = None,
        error: str | None = None,
    ) -> Response:
        if error:
            return _auth_error(401, "oidc_authorization_denied", "L'authentification OIDC a été refusée.")
        if not code or not state:
            return _auth_error(400, "oidc_callback_invalid", "Le callback OIDC est incomplet.")

        factory = request.app.state.session_factory
        transaction = consume_login_transaction(factory, state)
        if transaction is None:
            return _auth_error(
                400,
                "oidc_state_invalid",
                "La transaction de connexion OIDC est expirée ou invalide.",
            )
        try:
            identity = await oidc_runtime.client.exchange_code(
                code=code,
                code_verifier=transaction.code_verifier,
                nonce=transaction.nonce,
            )
        except (httpx.HTTPError, OidcProtocolError, ValueError):
            return _auth_error(
                401,
                "oidc_token_invalid",
                "La réponse OIDC n'a pas pu être validée.",
            )

        with factory() as session:
            principal = IdentityService(SqlUserIdentityRepository(session)).resolve(
                issuer=identity.issuer,
                subject=identity.subject,
                auth_mode="oidc",
            )
        if principal is None or principal.local_user_id is None:
            return _auth_error(
                403,
                "oidc_user_not_registered",
                "Cette identité Acumatica n'est pas autorisée dans RessourcePlanner.",
            )

        raw_session = create_server_session(
            factory,
            oidc_runtime,
            user_id=principal.local_user_id,
        )
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(
            oidc_runtime.cookie_name,
            raw_session,
            max_age=int(oidc_runtime.session_ttl.total_seconds()),
            httponly=True,
            secure=oidc_runtime.secure_cookie,
            samesite=oidc_runtime.cookie_samesite,
            path="/",
        )
        return response

    @router.post("/logout", status_code=204)
    def logout(request: Request) -> Response:
        factory = request.app.state.session_factory
        revoke_server_session(
            factory,
            cookie_name=oidc_runtime.cookie_name,
            request=request,
        )
        response = Response(status_code=204)
        response.delete_cookie(
            oidc_runtime.cookie_name,
            path="/",
            secure=oidc_runtime.secure_cookie,
            httponly=True,
            samesite=oidc_runtime.cookie_samesite,
        )
        return response

    return router
