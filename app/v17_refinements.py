from __future__ import annotations

"""Compatibility shim for historical V1.71 resource-management hooks.

The authoritative resource-management implementation now lives in
``resource_management_compat``. This module remains temporarily because V1.71
performance/local-preference installers still override a few entry points by name.
"""

from .resource_management_compat import (
    RESOURCE_ORDER_FIELD,
    SORT_ALPHA_ASC,
    SORT_ALPHA_DESC,
    SORT_AVAIL_ASC,
    SORT_AVAIL_DESC,
    SORT_MANUAL,
    SORT_OPTIONS,
    _ensure_manual_order_column,
    _manual_order_dialog,
    _new_resource_dialog,
    _order_number,
    _render_resources,
    _resource_order_map,
    _update_resource_profile_extended,
    install_resource_management_compat,
)


def install_v17_refinements() -> None:
    """Backward-compatible installer alias pending V1.71 extraction."""

    install_resource_management_compat()
