from __future__ import annotations

from typing import Any

from nicegui import ui as nicegui_ui

from . import ui as ui_module, v16
from .ui_context import ensure_scoped_ui


# Keep the validated CSS class name for layout compatibility. The historical V1.7
# renderer that originally owned the scroll-area override has been physically removed.
OPERATIONAL_SCROLL_CLASS = "v18-operational-scroll"


def _horizontal_container(*args: Any, **kwargs: Any) -> Any:
    """Retained layout helper for compatibility with any late-bound UI caller."""
    del args, kwargs
    return nicegui_ui.element("div").classes(OPERATIONAL_SCROLL_CLASS)


def install_operational_planning_compat() -> None:
    """Install the remaining scoped UI compatibility for operational planning.

    V1.6 still temporarily replaces its module-local ``select`` factory.
    ``ScopedNiceGUI`` keeps that override client/task-local instead of mutating
    process-wide NiceGUI state. The V1.7 renderer no longer exists and must not be
    imported or configured here.

    This module also owns the stable operational calendar dimensions. Keeping these
    compatibility details outside version-numbered installers makes the remaining
    historical renderer debt explicit while preserving the validated V1.8 layout.
    """
    if getattr(ui_module.PlannerUI, "_operational_planning_compat_installed", False):
        return

    ensure_scoped_ui(
        v16,
        scope_name="v16_planning",
        scoped_factories=("select",),
    )

    nicegui_ui.add_css(
        f"""
        .{OPERATIONAL_SCROLL_CLASS} {{
          width: 100%;
          height: auto !important;
          max-height: none !important;
          overflow-x: auto;
          overflow-y: visible;
          overscroll-behavior-x: contain;
        }}
        .schedule-grid {{
          grid-template-columns: repeat(8, minmax(0, 1fr)) !important;
          min-width: 1180px !important;
        }}
        """
    )

    ui_module.PlannerUI._operational_planning_compat_installed = True
