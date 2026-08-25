from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ResourceGroupingBindings:
    """Constants and ordering required by resource filtering/grouping."""

    all_classes: str
    all_resources: str
    unclassified: str
    resource_group_order: Callable[[str], Any]


def group_operational_planning_resources(
    techs: list[dict[str, Any]],
    class_map: dict[str, str],
    week_stats: dict[str, dict[str, Any]],
    class_filter: Any,
    resource_filter: Any,
    only_available: bool,
    *,
    bindings: ResourceGroupingBindings,
) -> dict[str, list[dict[str, Any]]]:
    """Filter visible resources and group them exactly as the operational grid expects."""

    filtered_techs: list[dict[str, Any]] = []
    for tech in techs:
        name = tech["name"]
        group = class_map.get(name, bindings.unclassified)
        if class_filter != bindings.all_classes and group != class_filter:
            continue
        if resource_filter != bindings.all_resources and name != resource_filter:
            continue
        if only_available and week_stats.get(name, {}).get("prudent_free", 0) <= 0.01:
            continue
        filtered_techs.append(tech)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for tech in filtered_techs:
        group = class_map.get(tech["name"], bindings.unclassified)
        grouped.setdefault(group, []).append(tech)

    for group in grouped:
        grouped[group].sort(
            key=lambda tech: (
                -week_stats.get(tech["name"], {}).get("prudent_free", 0.0),
                tech["name"],
            )
        )
    return grouped


def ordered_resource_group_names(
    grouped: dict[str, list[dict[str, Any]]],
    *,
    bindings: ResourceGroupingBindings,
) -> list[str]:
    return sorted(grouped, key=bindings.resource_group_order)


def resource_group_totals(
    group_techs: list[dict[str, Any]],
    week_stats: dict[str, dict[str, Any]],
) -> tuple[float, float]:
    total_free = sum(
        week_stats.get(tech["name"], {}).get("prudent_free", 0.0)
        for tech in group_techs
    )
    total_capacity = sum(
        week_stats.get(tech["name"], {}).get("capacity", 0.0)
        for tech in group_techs
    )
    return float(total_free), float(total_capacity)
