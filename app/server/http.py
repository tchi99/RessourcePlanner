from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Callable

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
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
from ..application.communications import CommunicationService, CommunicationTransportPort
from ..application.errors import ApplicationUnavailableError
from ..application.security import AuthPrincipal, ROLE_ADMIN
from ..infrastructure.sql import (
    SqlSessionFactory,
    create_session_factory,
    create_sql_engine,
    transactional_session,
)
from .composition import (
    build_communication_service,
    build_sql_facade,
    build_sql_idempotency_executor,
    build_sql_query_port,
    build_user_admin_service,
)
from .dev_user_switcher import DevUserSwitcherRuntime
from .oidc import OidcRuntime
from .performance import (
    InstrumentedJSONResponse,
    install_performance_middleware,
    install_sql_performance_instrumentation,
)
from .readiness import DatabaseReadinessError, check_database_readiness
from .routes_auth import build_auth_router
from .routes_commands import build_command_router
from .routes_competencies import build_competency_router
from .routes_communications import build_communication_router
from .routes_dev_user_switcher import build_dev_user_switcher_router
from .routes_integrations import build_integration_router
from .routes_me import build_me_router
from .routes_reads import build_read_router
from .routes_task_catalog import build_task_catalog_router
from .routes_user_admin import build_user_admin_router
from .security import AuthResolver, install_authorization_middleware, static_auth_resolver


SessionDependency = Callable[[], Iterator[Session]]
FacadeDependency = Callable[[], Iterator[ApplicationFacade]]
IdempotencyDependency = Callable[[], Iterator[IdempotentCommandExecutor]]
QueryDependency = Callable[[], Iterator[PlannerQueryPort]]
UserAdminDependency = Callable[..., Any]
CommunicationDependency = Callable[..., Any]


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


def make_communication_dependency(
    factory: SqlSessionFactory,
    *,
    session_dependency: SessionDependency | None = None,
    transport: CommunicationTransportPort | None = None,
) -> CommunicationDependency:
    request_session = session_dependency or make_session_dependency(factory)

    def dependency(
        session: Session = Depends(request_session),
    ) -> Iterator[CommunicationService]:
        yield build_communication_service(session, transport=transport)

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
    dev_user_switcher_runtime: DevUserSwitcherRuntime | None = None,
    communication_transport: CommunicationTransportPort | None = None,
    performance_log_path: Path | None = None,
    runtime_dependencies: dict[str, Any] | None = None,
) -> FastAPI:
    if oidc_runtime is not None and dev_user_switcher_runtime is not None:
        raise ValueError("OIDC et le sélecteur d’utilisateur de développement sont mutuellement exclusifs.")

    engine = create_sql_engine(database_url)
    install_sql_performance_instrumentation(engine)
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
    communication_dependency = make_communication_dependency(
        factory,
        session_dependency=session_dependency,
        transport=communication_transport,
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
        default_response_class=InstrumentedJSONResponse,
    )
    app.state.database_dialect = engine.dialect.name
    app.state.session_factory = factory
    app.state.facade_dependency = facade_dependency
    app.state.idempotency_dependency = idempotency_dependency
    app.state.query_dependency = query_dependency
    app.state.user_admin_dependency = user_admin_dependency
    app.state.communication_dependency = communication_dependency
    app.state.runtime_dependencies = dict(runtime_dependencies or {})
    app.state.dev_user_switcher_enabled = dev_user_switcher_runtime is not None

    install_authorization_middleware(
        app,
        auth_resolver or _default_auth_resolver(actor_name),
    )
    # Registered after authorization so Starlette wraps it outside auth and the
    # request performance context is already active while credentials are resolved.
    install_performance_middleware(app, log_path=performance_log_path)

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
    def health() -> dict[str, Any]:
        """Process liveness only; intentionally does not touch SQL or external systems."""
        return {
            "status": "ok",
            "api": "v1",
        }

    @app.get("/ready", tags=["system"], response_model=None)
    def readiness() -> Any:
        """Required local dependencies only; external integrations are informational."""
        dependencies = dict(app.state.runtime_dependencies)
        try:
            database = check_database_readiness(engine)
        except DatabaseReadinessError as exc:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "not_ready",
                    "api": "v1",
                    "database": {
                        "status": "error",
                        "reason": exc.code,
                    },
                    "external_dependencies": dependencies,
                },
            )
        return {
            "status": "ready",
            "api": "v1",
            "database": database,
            "external_dependencies": dependencies,
        }

    app.include_router(build_auth_router(oidc_runtime))
    if dev_user_switcher_runtime is not None:
        app.include_router(build_dev_user_switcher_router(dev_user_switcher_runtime))
    app.include_router(build_user_admin_router(user_admin_dependency))
    app.include_router(
        build_command_router(
            facade_dependency,
            idempotency_dependency,
            session_dependency,
        )
    )
    app.include_router(build_read_router(query_dependency))
    app.include_router(build_competency_router(session_dependency))
    app.include_router(build_task_catalog_router(session_dependency))
    app.include_router(build_me_router(query_dependency))
    app.include_router(build_communication_router(communication_dependency))
    app.include_router(
        build_integration_router(
            session_dependency,
            project_source=project_source,
            acumatica_info=acumatica_info,
        )
    )
    return app
