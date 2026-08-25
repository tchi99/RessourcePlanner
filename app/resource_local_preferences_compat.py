from __future__ import annotations

from . import operational_planning_sorting_compat as sorting_compat
from . import resource_management_compat as resource_management
from . import v17_refinements as legacy_resource_shim
from . import v17_sort_fix as legacy_sort_shim
from .resource_local_preferences import install_resource_local_preferences


def install_resource_local_preferences_compat() -> None:
    """Install local preferences and mirror hooks into temporary V1.7 shims."""

    install_resource_local_preferences()

    # Temporary bridge only. These assignments disappear when the remaining V1.7
    # shims are physically removed in the next cleanup step.
    legacy_resource_shim._resource_order_map = resource_management._resource_order_map
    legacy_resource_shim._manual_order_dialog = resource_management._manual_order_dialog
    legacy_resource_shim._new_resource_dialog = resource_management._new_resource_dialog
    legacy_sort_shim._move_manual_resource = sorting_compat.move_manual_resource
