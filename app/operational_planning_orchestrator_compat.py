from __future__ import annotations

from . import v13, v15, v15_engine, v16
from .bugfixes import schedulable_technicians
from .operational_planning_drop_handler_compat import (
    operational_planning_drop_handler_bindings,
)
from .operational_planning_header_filters_compat import (
    operational_planning_header_filter_bindings,
)
from .operational_planning_orchestrator import OperationalPlanningBindings
from .operational_planning_resource_groups_compat import (
    operational_planning_resource_group_bindings,
)
from .operational_planning_resource_row_compat import (
    operational_planning_resource_row_bindings,
)
from .operational_planning_work_sections_compat import (
    operational_planning_work_sections_bindings,
)
from .services import week_days


def operational_planning_bindings() -> OperationalPlanningBindings:
    """Compose the stable orchestrator from transitional V1.x data providers."""

    return OperationalPlanningBindings(
        week_days=week_days,
        schedulable_technicians=schedulable_technicians,
        resource_class_map=v16.resource_class_map,
        weekly_resource_stats=v16._weekly_resource_stats,
        demand_lookup=v16._demand_lookup,
        segment_records=v13.segment_records,
        allocation_records=v15_engine.allocation_records,
        unassigned_segments_for_week=v15._unassigned_segments_for_week,
        pending_demands_for_week=v15._pending_demands_for_week,
        drop_bindings=operational_planning_drop_handler_bindings(),
        row_bindings=operational_planning_resource_row_bindings(),
        work_sections_bindings=operational_planning_work_sections_bindings(),
        header_filter_bindings=operational_planning_header_filter_bindings(),
        resource_group_bindings=operational_planning_resource_group_bindings(),
    )
