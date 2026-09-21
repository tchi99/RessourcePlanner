from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, TypeVar


ResultT = TypeVar("ResultT")


class ApplicationError(Exception):
    """Transport-agnostic application failure.

    ``code`` is stable enough for an API/UI adapter to translate the failure without
    inspecting a French message. ``context`` contains only structured diagnostic
    values and must not contain transport or persistence objects.
    """

    default_code = "application_error"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        self.message = str(message)
        self.code = str(code or self.default_code)
        self.context = dict(context or {})
        super().__init__(self.message)

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "context": dict(self.context),
        }


class ApplicationAuthorizationError(ApplicationError):
    default_code = "permission_denied"


class ApplicationValidationError(ApplicationError):
    default_code = "validation_error"


class ApplicationNotFoundError(ApplicationError):
    default_code = "not_found"


class ApplicationConflictError(ApplicationError):
    default_code = "conflict"


class ApplicationUnavailableError(ApplicationError):
    default_code = "unavailable"


class ApplicationOperationError(ApplicationError):
    default_code = "operation_failed"


def application_error_from_exception(
    exc: Exception,
    *,
    code_prefix: str,
    context: Mapping[str, Any] | None = None,
) -> ApplicationError:
    """Translate a legacy adapter failure to the stable application error contract."""

    if isinstance(exc, ApplicationError):
        return exc

    message = str(exc)
    if isinstance(exc, KeyError) and exc.args:
        message = str(exc.args[0])
    if not message:
        message = "L'opération n'a pas pu être complétée."

    if isinstance(exc, KeyError):
        return ApplicationNotFoundError(
            message,
            code=f"{code_prefix}_not_found",
            context=context,
        )
    if isinstance(exc, ValueError):
        return ApplicationValidationError(
            message,
            code=f"{code_prefix}_invalid",
            context=context,
        )
    return ApplicationOperationError(
        message,
        code=f"{code_prefix}_failed",
        context=context,
    )


def call_application_port(
    action: Callable[[], ResultT],
    *,
    code_prefix: str,
    context: Mapping[str, Any] | None = None,
) -> ResultT:
    """Execute one port call and expose only structured application failures."""

    try:
        return action()
    except ApplicationError:
        raise
    except Exception as exc:
        raise application_error_from_exception(
            exc,
            code_prefix=code_prefix,
            context=context,
        ) from exc
