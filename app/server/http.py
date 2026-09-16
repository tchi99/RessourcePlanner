from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import Iterator
from typing import Any, Callable

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..application import (
    ApplicationConflictError,
    ApplicationError,
    ApplicationFacade,
    ApplicationNotFoundError,
    ApplicationOperationError,
    ApplicationValidationError,
    IdempotentCommandExecutor,
    PlannerQueryPort,
    ProjectSourcePort,
)
from ..application.errors import ApplicationUnavailableError
from ..application.security import AuthPrincipal, ROLE_ADMIN
from ..infrastructure.sql import (
    SqlSessionFactory,
    create_session_factory,
    create_sql_engine,
    transactional_session,
)
from .composition import (
    build_sql_facade,
    build_sql_idempotency_executor,
    build_sql_query_port,
    build_user_admin_service,
)
from .oidc import OidcRuntime
from .routes_auth import build_auth_router
from .routes_commands import build_command_router
from .routes_integrations import build_integration_router
from .routes_reads import build_read_router
from .routes_user_admin import build_user_admin_router
from .security import AuthResolver, install_authorization_middleware, static_auth_resolver


SessionDependency = Callable[[], Iterator[Session]]
FacadeDependency = Callable[[], Iterator[ApplicationFacade]]
IdempotencyDependency = Callable[[], Iterator[IdempotentCommandExecutor]]
QueryDependency = Callable[[], Iterator[PlannerQueryPort]]
UserAdminDependency = Callable[..., Any]


def application_error_status(exc: ApplicationError) -> int:
    if isinstance(exc, ApplicationValidationError):
        return 422
    if isinstance(exc, ApplicationNotFoundError):
        return 404
    if isinstance(exc, ApplicationConflictError):
        return 409
    if isinstance(exc, ApplicationUnavailableError):
        return 503
    if isinstance(exc, ApplicationOperationError):
        return 500
    return 400


def application_error_response(exc: ApplicationError) -> JSONResponse:
    return JSONResponse(
        status_code=application_error_status(exc),
        content={"error": exc.as_dict()},
    )


def make_session_dependency(factory: SqlSessionFactory) -> SessionDependency:
    def dependency() -> Iterator[Session]:
        with transactional_session(factory) as session:
            yield session

    return dependency


def _request_actor(request: Request, fallback: str) -> str:
    principal: AuthPrincipal | None = getattr(request.state, "auth_principal", None)
    return principal.display_name if principal is not None else fallback


def make_facade_dependency(
    factory: SqlSessionFactory,
    *,
    actor_name: str = "api",
    session_dependency: SessionDependency | None = None,
) -> FacadeDependency:
    request_session = session_dependency or make_session_dependency(factory)

    def dependency(
        request: Request,
        session: Session = Depends(request_session),
    ) -> Iterator[ApplicationFacade]:
        yield build_sql_facade(session, actor_name=_request_actor(request, actor_name))

    return dependency


def make_idempotency_dependency(
    factory: SqlSessionFactory,
    *,
    actor_name: str = "api",
    session_dependency: SessionDependency | None = None,
) -> IdempotencyDependency:
    request_session = session_dependency or make_session_dependency(factory)

    def dependency(
        request: Request,
        session: Session = Depends(request_session),
    ) -> Iterator[IdempotentCommandExecutor]:
        yield build_sql_idempotency_executor(
            session,
            actor_name=_request_actor(request, actor_name),
        )

    return dependency


def make_query_dependency(
    factory: SqlSessionFactory,
    *,
    session_dependency: SessionDependency | None = None,
) -> QueryDependency:
    request_session = session_dependency or make_session_dependency(factory)

    def dependency(
        session: Session = Depends(request_session),
    ) -> Iterator[PlannerQueryPort]:
        yield build_sql_query_port(session)

    return dependency


def make_user_admin_dependency(
    factory: SqlSessionFactory,
    *,
    session_dependency: SessionDependency | None = None,
) -> UserAdminDependency:
    request_session = session_dependency or make_session_dependency(factory)

    def dependency(
        session: Session = Depends(request_session),
    ) -> Iterator[Any]:
        yield build_user_admin_service(session)

    return dependency


def _request_validation_response(exc: RequestValidationError) -> JSONResponse:
    details = [
        {
            "location": [str(item) for item in error.get("loc", ())],
            "message": str(error.get("msg") or "Valeur invalide"),
            "type": str(error.get("type") or "validation_error"),
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "request_validation_error",
                "message": "La requête HTTP est invalide.",
                "context": {"errors": details},
            }
        },
    )


def _default_auth_resolver(actor_name: str) -> AuthResolver:
    """Keep direct API construction backward compatible while still exercising auth."""

    principal = AuthPrincipal.from_roles(
        local_user_id=None,
        issuer="urn:resourceplanner:test",
        subject="test-admin",
        display_name=actor_name,
        email=None,
        roles=(ROLE_ADMIN,),
        auth_mode="test",
    )
    return static_auth_resolver(principal)


def create_api_app(
    database_url: str,
    *,
    actor_name: str = "api",
    project_source: ProjectSourcePort | None = None,
    acumatica_info: dict[str, Any] | None = None,
    auth_resolver: AuthResolver | None = None,
    oidc_runtime: OidcRuntime | None = None,
) -> FastAPI:
    engine = create_sql_engine(database_url)
    factory = create_session_factory(engine)
    session_dependency = make_session_dependency(factory)
    facade_dependency = make_facade_dependency(
        factory,
        actor_name=actor_name,
        session_dependency=session_dependency,
    )
    idempotency_dependency = make_idempotency_dependency(
        factory,
        actor_name=actor_name,
        session_dependency=session_dependency,
    )
    query_dependency = make_query_dependency(
        factory,
        session_dependency=session_dependency,
    )
    user_admin_dependency = make_user_admin_dependency(
        factory,
        session_dependency=session_dependency,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            engine.dispose()

    app = FastAPI(
        title="RessourcePlanner API",
        version="1.0.0-dev",
        lifespan=lifespan,
    )
    app.state.database_dialect = engine.dialect.name
    app.state.session_factory = factory
    app.state.facade_dependency = facade_dependency
    app.state.idempotency_dependency = idempotency_dependency
    app.state.query_dependency = query_dependency
    app.state.user_admin_dependency = user_admin_dependency

    install_authorization_middleware(
        app,
        auth_resolver or _default_auth_resolver(actor_name),
    )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return _request_validation_response(exc)

    @app.exception_handler(ApplicationError)
    async def handle_application_error(
        _request: Request,
        exc: ApplicationError,
    ) -> JSONResponse:
        return application_error_response(exc)

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        _request: Request,
        _exc: Exception,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Une erreur interne est survenue.",
                    "context": {},
                }
            },
        )

    @app.get("/health", tags=["system"])
    def health(session: Session = Depends(session_dependency)) -> dict[str, Any]:
        session.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "database": engine.dialect.name,
            "api": "v1",
        }

    app.include_router(build_auth_router(oidc_runtime))
    app.include_router(build_user_admin_router(user_admin_dependency))
    app.include_router(build_command_router(facade_dependency, idempotency_dependency))
    app.include_router(build_read_router(query_dependency))
    app.include_router(
        build_integration_router(
            session_dependency,
            project_source=project_source,
            acumatica_info=acumatica_info,
        )
    )
    return app
