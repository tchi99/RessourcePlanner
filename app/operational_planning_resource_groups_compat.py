from __future__ import annotations

from . import v16
from .operational_planning_resource_groups import ResourceGroupingBindings


def operational_planning_resource_group_bindings() -> ResourceGroupingBindings:
    """Compose resource grouping from transitional V1.x constants/helpers."""

    return ResourceGroupingBindings(
        all_classes=v16.ALL_CLASSES,
        all_resources=v16.ALL_RESOURCES,
        unclassified=v16.UNCLASSIFIED,
        resource_group_order=v16._resource_group_order,
    )
