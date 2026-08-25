from __future__ import annotations

"""Compatibility shim for the extracted local resource-preference adapter."""

from .resource_local_preferences import (
    LOCAL_PREFERENCES_FILE,
    PREFERENCES_VERSION,
    _clean_order_map,
    _load_preferences,
    _local_order_map_factory,
    _manual_order_dialog_local,
    _move_manual_resource_local,
    _new_resource_dialog_local,
    _orders_section,
    _refresh_local_preference,
    _save_preferences,
    _workbook_key,
    _write_local_orders,
)
from .resource_local_preferences_compat import install_resource_local_preferences_compat


def install_v171_local_preferences() -> None:
    """Backward-compatible installer alias."""

    install_resource_local_preferences_compat()
