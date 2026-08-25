from __future__ import annotations

from collections.abc import Mapping
from typing import Any


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


class ApplicationValidationError(ApplicationError):
    default_code = "validation_error"


class ApplicationNotFoundError(ApplicationError):
    default_code = "not_found"


class ApplicationConflictError(ApplicationError):
    default_code = "conflict"


class ApplicationOperationError(ApplicationError):
    default_code = "operation_failed"
