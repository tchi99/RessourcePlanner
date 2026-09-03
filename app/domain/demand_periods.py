from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Mapping, Sequence

from .confirmation import normalize_confirmation


PERIOD_KIND_CUMULATIVE = "CUMULATIVE"
PERIOD_KIND_ALTERNATIVE = "ALTERNATIVE"
VALID_PERIOD_KINDS = {PERIOD_KIND_CUMULATIVE, PERIOD_KIND_ALTERNATIVE}


@dataclass(frozen=True, slots=True)
class DemandPeriodDefinition:
    """One requested work period independent of persistence and UI.

    CUMULATIVE periods add workload. ALTERNATIVE periods belong to an exclusive
    group: zero or one option from each group may become effective.
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
        # Confirmation is a business dimension independent from approval.
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
    """Return periods that may materialize into requirements without double-counting.

    All cumulative periods are effective. For an alternative group, only the selected
    period is effective. An unresolved group contributes no operational requirement.
    """

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
    """Project potential workload while counting an exclusive group only once.

    When a group is already resolved, its selected option is used. Otherwise the
    largest option is used as the conservative projected load for that group.
    """

    validate_period_definitions(periods)
    chosen = dict(selections or {})
    if chosen:
        # Also validates selection/group consistency.
        effective_period_ids(periods, chosen)

    total = 0.0
    alternatives: dict[str, list[DemandPeriodDefinition]] = {}
    for period in periods:
        if period.kind.upper() == PERIOD_KIND_CUMULATIVE:
            total += float(period.hours) * period.resource_count
        else:
            alternatives.setdefault(_text(period.alternative_group), []).append(period)

    for group, options in alternatives.items():
        selected_id = chosen.get(group)
        if selected_id:
            selected = next(period for period in options if period.period_id == selected_id)
            total += float(selected.hours) * selected.resource_count
        else:
            total += max(float(period.hours) * period.resource_count for period in options)
    return round(total, 2)
