from __future__ import annotations

from . import v15_refinements, v16, v16_refinements
from .operational_planning_header_filters import HeaderFilterBindings


def operational_planning_header_filter_bindings() -> HeaderFilterBindings:
    """Compose the extracted planning header from transitional V1.x helpers."""

    return HeaderFilterBindings(
        all_classes=v16.ALL_CLASSES,
        resource_classes=v16.RESOURCE_CLASSES,
        unclassified=v16.UNCLASSIFIED,
        all_resources=v16.ALL_RESOURCES,
        all_projects=v16.ALL_PROJECTS,
        all_confirmations=v16.ALL_CONFIRMATIONS,
        filter_value=v16._filter_value,
        set_filter=v16._set_planning_filter,
        project_labels=v16_refinements._project_labels,
        open_manual_allocation=lambda owner: v15_refinements._open_allocation_dialog(owner),
        recalculate=lambda owner: v15_refinements._recalculate(owner),
    )
