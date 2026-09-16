from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_DOWN


CENT = Decimal("0.01")


def normalize_active_day_target(
    value: object,
    *,
    start: date | None = None,
    end: date | None = None,
    field: str = "jours actifs",
) -> int | None:
    """Normalize an optional desired active-day count without inventing work hours.

    Active days are a distribution target, not an alternate duration-to-hours formula.
    A target must therefore be a positive whole number and cannot exceed the absolute
    number of calendar dates in its requested window.
    """

    if value in (None, ""):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} doit être un nombre entier positif.") from exc
    if numeric <= 0 or not numeric.is_integer():
        raise ValueError(f"{field} doit être un nombre entier positif.")
    target = int(numeric)
    if start is not None and end is not None:
        if end < start:
            raise ValueError("La fenêtre de planification est invalide.")
        available_dates = (end - start).days + 1
        if target > available_dates:
            raise ValueError(
                f"{field} ({target}) dépasse les {available_dates} date(s) de la fenêtre demandée."
            )
    return target


def split_total_workforce_hours(total_hours: object, resource_count: int) -> tuple[float, ...]:
    """Split authoritative total workforce hours across independent resources.

    The returned values preserve the total to cent precision. ``resource_count`` is
    parallelism; it never multiplies the requested workload.
    """

    count = int(resource_count)
    if count < 1:
        raise ValueError("Le nombre de ressources doit être au moins 1.")
    total = Decimal(str(total_hours)).quantize(CENT)
    if total <= 0:
        raise ValueError("Les heures totales doivent être supérieures à zéro.")

    base = (total / Decimal(count)).quantize(CENT, rounding=ROUND_DOWN)
    result = [base for _ in range(count)]
    remainder = total - (base * count)
    cents = int((remainder / CENT).to_integral_value())
    for index in range(cents):
        result[index] += CENT
    return tuple(float(value) for value in result)
