"""FastAPI/SQL server boundary for RessourcePlanner."""

from .composition import build_sql_facade, build_sql_query_port
from .http import (
    application_error_response,
    application_error_status,
    create_api_app,
    make_facade_dependency,
    make_query_dependency,
    make_session_dependency,
)
from .runtime import (
    ServerConfigurationError,
    ServerSettings,
    create_configured_app,
    run_server,
)

__all__ = [
    "ServerConfigurationError",
    "ServerSettings",
    "application_error_response",
    "application_error_status",
    "build_sql_facade",
    "build_sql_query_port",
    "create_api_app",
    "create_configured_app",
    "make_facade_dependency",
    "make_query_dependency",
    "make_session_dependency",
    "run_server",
]
