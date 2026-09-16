from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Mapping, Sequence

from .active_days import normalize_active_day_target
from .confirmation import normalize_confirmation


PERIOD_KIND_CUMULATIVE = "CUMULATIVE"
PERIOD_KIND_ALTERNATIVE = "ALTERNATIVE"
VALID_PERIOD_KINDS = {PERIOD_KIND_CUMULATIVE, PERIOD_KIND_ALTERNATIVE}


@dataclass(frozen=True, slots=True)
class DemandPeriodDefinition:
    """One requested work period independent of persistence and UI.

    ``hours`` is the total workforce effort for the period. ``resource_count`` is the
    desired parallelism and never multiplies that effort. ``desired_active_days`` is a
    distribution target for flexible planning, not an alternate hours formula.
    """

    period_id: str
    start_date: date
    end_date: date
    hours: float
    kind: str = PERIOD_KIND_CUMULATIVE
    alternative_group: str | None = None
    confirmation: str = "Tentative"
    proposed_resource: str | None = None
    resource_count: int = 1
    desired_active_days: int | None = None
    note: str | None = None


def _text(value: object) -> str:
    return str(value or "").strip()


def validate_period_definitions(periods: Sequence[DemandPeriodDefinition]) -> None:
    ids: set[str] = set()
    group_counts: dict[str, int] = {}
    for period in periods:
        identifier = _text(period.period_id)
        if not identifier:
            raise ValueError("Chaque période de demande doit avoir un identifiant stable.")
        if identifier in ids:
            raise ValueError(f"Identifiant de période dupliqué: {identifier}")
        ids.add(identifier)
        if period.end_date < period.start_date:
            raise ValueError(
                f"La période {identifier} se termine avant sa date de début."
            )
        if period.hours <= 0:
            raise ValueError(f"Les heures de la période {identifier} doivent être positives.")
        if period.resource_count < 1:
            raise ValueError(
                f"Le nombre de ressources de la période {identifier} doit être au moins 1."
            )
        normalize_active_day_target(
            period.desired_active_days,
            start=period.start_date,
            end=period.end_date,
            field=f"Les jours actifs de la période {identifier}",
        )
        normalize_confirmation(period.confirmation)

        kind = _text(period.kind).upper()
        if kind not in VALID_PERIOD_KINDS:
            raise ValueError(f"Type de période non supporté: {period.kind}")
        group = _text(period.alternative_group)
        if kind == PERIOD_KIND_ALTERNATIVE:
            if not group:
                raise ValueError(
                    f"La période alternative {identifier} doit appartenir à un groupe."
                )
            group_counts[group] = group_counts.get(group, 0) + 1
        elif group:
            raise ValueError(
                f"La période cumulative {identifier} ne peut pas avoir de groupe alternatif."
            )

    singleton_groups = sorted(group for group, count in group_counts.items() if count < 2)
    if singleton_groups:
        raise ValueError(
            "Un groupe alternatif doit contenir au moins deux options: "
            + ", ".join(singleton_groups)
        )


def effective_period_ids(
    periods: Sequence[DemandPeriodDefinition],
    selections: Mapping[str, str],
) -> tuple[str, ...]:
    """Return periods that may materialize into requirements without double-counting."""

    validate_period_definitions(periods)
    period_by_id = {period.period_id: period for period in periods}
    for group, period_id in selections.items():
        selected = period_by_id.get(period_id)
        if selected is None:
            raise ValueError(
                f"La sélection {period_id} du groupe {group} ne correspond à aucune période."
            )
        if selected.kind.upper() != PERIOD_KIND_ALTERNATIVE:
            raise ValueError(f"La période {period_id} n'est pas une option alternative.")
        if _text(selected.alternative_group) != _text(group):
            raise ValueError(
                f"La période {period_id} n'appartient pas au groupe alternatif {group}."
            )

    effective: list[str] = []
    for period in periods:
        if period.kind.upper() == PERIOD_KIND_CUMULATIVE:
            effective.append(period.period_id)
            continue
        group = _text(period.alternative_group)
        if selections.get(group) == period.period_id:
            effective.append(period.period_id)
    return tuple(effective)


def projected_hours_without_double_counting(
    periods: Sequence[DemandPeriodDefinition],
    selections: Mapping[str, str] | None = None,
) -> float:
    """Project total workforce effort while counting an exclusive group only once."""

    validate_period_definitions(periods)
    chosen = dict(selections or {})
    if chosen:
        effective_period_ids(periods, chosen)

    total = 0.0
    alternatives: dict[str, list[DemandPeriodDefinition]] = {}
    for period in periods:
        if period.kind.upper() == PERIOD_KIND_CUMULATIVE:
            total += float(period.hours)
        else:
            alternatives.setdefault(_text(period.alternative_group), []).append(period)

    for group, options in alternatives.items():
        selected_id = chosen.get(group)
        if selected_id:
            selected = next(period for period in options if period.period_id == selected_id)
            total += float(selected.hours)
        else:
            total += max(float(period.hours) for period in options)
    return round(total, 2)


def projected_hours_in_window(
    total_hours: float,
    start_date: date,
    end_date: date,
    window_start: date,
    window_end: date,
) -> float:
    """Spread a macro workload over its date range and return the window share.

    Medium-term ranges do not contain daily shifts yet. Their hours are therefore
    spread proportionally over weekdays. Weekend-only ranges fall back to calendar
    days so a legitimate weekend request is never projected as zero.
    """

    if end_date < start_date:
        raise ValueError("La date de fin de la charge ne peut pas précéder son début.")
    if window_end < window_start:
        raise ValueError("La fenêtre de projection est invalide.")
    hours = max(float(total_hours or 0.0), 0.0)
    if hours <= 0 or end_date < window_start or start_date > window_end:
        return 0.0

    clipped_start = max(start_date, window_start)
    clipped_end = min(end_date, window_end)

    def day_count(start: date, end: date, *, weekdays_only: bool) -> int:
        count = 0
        cursor = start
        while cursor <= end:
            if not weekdays_only or cursor.weekday() < 5:
                count += 1
            cursor += timedelta(days=1)
        return count

    total_days = day_count(start_date, end_date, weekdays_only=True)
    overlap_days = day_count(clipped_start, clipped_end, weekdays_only=True)
    if total_days == 0:
        total_days = day_count(start_date, end_date, weekdays_only=False)
        overlap_days = day_count(clipped_start, clipped_end, weekdays_only=False)
    return round(hours * overlap_days / total_days, 2) if total_days else 0.0


def projected_period_hours_in_window_without_double_counting(
    periods: Sequence[DemandPeriodDefinition],
    window_start: date,
    window_end: date,
    selections: Mapping[str, str] | None = None,
) -> float:
    """Project period workload into one window without summing exclusive options."""

    validate_period_definitions(periods)
    chosen = dict(selections or {})
    if chosen:
        effective_period_ids(periods, chosen)

    def contribution(period: DemandPeriodDefinition) -> float:
        return projected_hours_in_window(
            float(period.hours),
            period.start_date,
            period.end_date,
            window_start,
            window_end,
        )

    total = 0.0
    alternatives: dict[str, list[DemandPeriodDefinition]] = {}
    for period in periods:
        if period.kind.upper() == PERIOD_KIND_CUMULATIVE:
            total += contribution(period)
        else:
            alternatives.setdefault(_text(period.alternative_group), []).append(period)

    for group, options in alternatives.items():
        selected_id = chosen.get(group)
        if selected_id:
            selected = next(period for period in options if period.period_id == selected_id)
            total += contribution(selected)
        else:
            total += max(contribution(period) for period in options)
    return round(total, 2)
