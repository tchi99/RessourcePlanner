from __future__ import annotations

from . import features, v13, v15, v15_engine, v16
from .operational_planning_drag_drop import make_draggable, make_drop_zone
from .operational_planning_resource_row import ResourceRowBindings
from .operational_shift_editor_compat import (
    allocation_confirmation,
    allocation_style,
    demand_confirmation,
    is_missing_allocation,
    open_allocation_dialog,
)


def operational_planning_resource_row_bindings() -> ResourceRowBindings:
    """Compose the extracted row renderer from transitional V1.x helpers.

    This is an explicit compatibility boundary. Keeping these versioned imports here
    prevents the extracted renderer and the V1.7 renderer from owning the wiring.
    """
    return ResourceRowBindings(
        make_drop_zone=make_drop_zone,
        availability_for_day=features.availability_for_day,
        availability_hours=v13._availability_hours,
        all_projects=v16.ALL_PROJECTS,
        project_number_for_allocation=v16._project_number_for_allocation,
        all_confirmations=v16.ALL_CONFIRMATIONS,
        demand_confirmation=demand_confirmation,
        allocation_confirmation=allocation_confirmation,
        is_missing_allocation=is_missing_allocation,
        pending_covers_day=v15._pending_covers_day,
        number=v13._number,
        truthy=v15_engine._truthy,
        allocation_style=allocation_style,
        open_allocation_dialog=open_allocation_dialog,
        make_draggable=make_draggable,
    )
