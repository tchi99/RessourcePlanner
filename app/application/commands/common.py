from __future__ import annotations

from datetime import date, datetime
from typing import Final

from ..errors import ApplicationValidationError


class UnsetType:
    __slots__ = ()

    def __repr__(self) -> str:
        return "UNSET"


UNSET: Final = UnsetType()


def text(value: object) -> str:
    return str(value or "").strip()


def optional_text(value: object) -> str | None:
    normalized = text(value)
    return normalized or None


def required_text(value: object, *, field: str, message: str) -> str:
    normalized = text(value)
    if not normalized:
        raise ApplicationValidationError(
            message,
            code=f"{field}_required",
            context={"field": field},
        )
    return normalized


def date_value(value: object, *, field: str, required: bool) -> date | None:
    if value in (None, ""):
        if required:
            raise ApplicationValidationError(
                f"Le champ {field} est requis.",
                code=f"{field}_required",
                context={"field": field},
            )
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = text(value)
    try:
        return date.fromisoformat(raw[:10])
    except ValueError as exc:
        raise ApplicationValidationError(
            f"La valeur de {field} n'est pas une date valide.",
            code=f"{field}_invalid",
            context={"field": field, "value": raw},
        ) from exc


def float_value(
    value: object,
    *,
    field: str,
    required: bool = False,
    minimum: float | None = None,
) -> float | None:
    if value in (None, ""):
        if required:
            raise ApplicationValidationError(
                f"Le champ {field} est requis.",
                code=f"{field}_required",
                context={"field": field},
            )
        return None
    try:
        result = float(str(value).replace(",", "."))
    except (TypeError, ValueError) as exc:
        raise ApplicationValidationError(
            f"La valeur de {field} doit être numérique.",
            code=f"{field}_invalid",
            context={"field": field, "value": value},
        ) from exc
    if minimum is not None and result < minimum:
        raise ApplicationValidationError(
            f"La valeur de {field} doit être au moins {minimum:g}.",
            code=f"{field}_too_small",
            context={"field": field, "minimum": minimum, "value": result},
        )
    return round(result, 2)


def int_value(
    value: object,
    *,
    field: str,
    default: int | None = None,
    minimum: int | None = None,
) -> int | None:
    if value in (None, ""):
        return default
    try:
        result = int(float(str(value).replace(",", ".")))
    except (TypeError, ValueError) as exc:
        raise ApplicationValidationError(
            f"La valeur de {field} doit être un nombre entier.",
            code=f"{field}_invalid",
            context={"field": field, "value": value},
        ) from exc
    if minimum is not None and result < minimum:
        raise ApplicationValidationError(
            f"La valeur de {field} doit être au moins {minimum}.",
            code=f"{field}_too_small",
            context={"field": field, "minimum": minimum, "value": result},
        )
    return result


def bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return text(value).lower() in {"1", "true", "yes", "oui", "x"}


def validate_date_window(start: date | None, end: date | None, *, prefix: str) -> None:
    if start is not None and end is not None and end < start:
        raise ApplicationValidationError(
            "La date de fin ne peut pas précéder la date de début.",
            code=f"{prefix}_date_window_invalid",
            context={"start": start.isoformat(), "end": end.isoformat()},
        )
