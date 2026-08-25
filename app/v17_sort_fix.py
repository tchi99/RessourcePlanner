from __future__ import annotations

"""Compatibility shim for historical V1.7.1 imports.

The authoritative operational-planning sorting implementation now lives in
``operational_planning_sorting`` and ``operational_planning_sorting_compat``.
This module is intentionally absent from the runtime composition manifest and may be
removed once the remaining V1.71 compatibility installers stop importing it.
"""

from .operational_planning_sorting import alpha_key as _alpha_key
from .operational_planning_sorting import set_resource_sort as _set_resource_sort
from .operational_planning_sorting_compat import (
    install_operational_planning_sorting,
    manual_order_script as _manual_order_script,
    move_manual_resource as _move_manual_resource,
    ranked_weekly_stats as _ranked_weekly_stats,
    register_manual_order_handler as _register_manual_order_handler,
)


def install_v17_sort_fix() -> None:
    """Backward-compatible alias; no longer part of runtime composition."""

    install_operational_planning_sorting()
