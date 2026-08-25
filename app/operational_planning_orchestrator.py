from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .operational_planning_drop_handler import (
    DropHandlerBindings,
    register_operational_planning_drop_handler,
)
from .operational_planning_grid import render_operational_planning_grid
from .operational_planning_header_filters import (
    HeaderFilterBindings,
    render_operational_planning_header_filters,
    resolve_planning_filter_state,
)
from .operational_planning_resource_groups import (
    ResourceGroupingBindings,
    group_operational_planning_resources,
)
from .operational_planning_resource_row import ResourceRowBindings
from .operational_planning_work_sections import (
    WorkSectionsBindings,
    render_operational_planning_work_sections,
)


@dataclass(frozen=True)
class OperationalPlanningBindings:
    """All dependencies needed to orchestrate one operational-planning render."""

    week_days: Callable[[Any], list[Any]]
    schedulable_technicians: Callable[[Any], list[dict[str, Any]]]
    resource_class_map: Callable[[Any], dict[str, str]]
    weekly_resource_stats: Callable[[Any, Any], dict[str, dict[str, Any]]]
    demand_lookup: Callable[[Any], dict[str, dict[str, Any]]]
    segment_records: Callable[..., list[dict[str, Any]]]
    allocation_records: Callable[[Any], list[dict[str, Any]]]
    unassigned_segments_for_week: Callable[[Any, Any], list[dict[str, Any]]]
    pending_demands_for_week: Callable[[Any, Any], list[dict[str, Any]]]
    drop_bindings: DropHandlerBindings
    row_bindings: ResourceRowBindings
    work_sections_bindings: WorkSectionsBindings
    header_filter_bindings: HeaderFilterBindings
    resource_group_bindings: ResourceGroupingBindings


def render_operational_planning(
    owner: Any,
    *,
    weekly_stats_provider: Callable[[Any, Any], dict[str, dict[str, Any]]] | None = None,
    bindings: OperationalPlanningBindings,
) -> None:
    """Collect planning data and compose all non-versioned operational renderers."""

    register_operational_planning_drop_handler(owner, bindings=bindings.drop_bindings)

    days = bindings.week_days(owner.current_week)
    techs = bindings.schedulable_technicians(owner.repo)
    class_map = bindings.resource_class_map(owner.repo)
    stats_provider = weekly_stats_provider or bindings.weekly_resource_stats
    week_stats = stats_provider(owner.repo, owner.current_week)
    demands = bindings.demand_lookup(owner.repo)
    segments = {
        str(row.get("IDSegment") or ""): row
        for row in bindings.segment_records(owner.repo, include_cancelled=False)
    }
    allocations = [
        row
        for row in bindings.allocation_records(owner.repo)
        if row.get("Date") and days[0] <= row["Date"] <= days[-1]
    ]
    unassigned = bindings.unassigned_segments_for_week(owner.repo, owner.current_week)
    pending = bindings.pending_demands_for_week(owner.repo, owner.current_week)

    filter_state = resolve_planning_filter_state(
        owner,
        allocations,
        unassigned,
        pending,
        bindings=bindings.header_filter_bindings,
    )
    render_operational_planning_header_filters(
        owner,
        days,
        techs,
        filter_state,
        bindings=bindings.header_filter_bindings,
    )

    render_operational_planning_work_sections(
        owner,
        unassigned,
        pending,
        demands,
        filter_state.project_filter,
        filter_state.confirmation_filter,
        bindings=bindings.work_sections_bindings,
    )

    grouped = group_operational_planning_resources(
        techs,
        class_map,
        week_stats,
        filter_state.class_filter,
        filter_state.resource_filter,
        filter_state.only_available,
        bindings=bindings.resource_group_bindings,
    )

    render_operational_planning_grid(
        owner,
        days,
        grouped,
        allocations,
        segments,
        demands,
        pending,
        week_stats,
        filter_state.project_filter,
        filter_state.confirmation_filter,
        resource_group_bindings=bindings.resource_group_bindings,
        row_bindings=bindings.row_bindings,
    )
