from __future__ import annotations

from typing import Any

from nicegui import ui as nicegui_ui

from . import ui as ui_module, v16, v17
from .ui_context import ensure_scoped_ui


# Keep the validated CSS class name while the renderer is still historical. The
# installer/module is no longer version-numbered, but changing the DOM class is not
# required for this architecture-only tranche and could break local styling hooks.
OPERATIONAL_SCROLL_CLASS = "v18-operational-scroll"


def _horizontal_container(*args: Any, **kwargs: Any) -> Any:
    del args, kwargs
    return nicegui_ui.element("div").classes(OPERATIONAL_SCROLL_CLASS)


def install_operational_planning_compat() -> None:
    """Install the remaining scoped UI compatibility for operational planning.

    The V1.6/V1.7 renderers still temporarily replace their module-local ``select``
    factory. ``ScopedNiceGUI`` keeps those overrides client/task-local instead of
    mutating process-wide NiceGUI state. The V1.7 renderer also receives a simple
    horizontal overflow container in place of Quasar ``scroll_area``.

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
    ensure_scoped_ui(
        v17,
        scope_name="v17_planning",
        scoped_factories=("select",),
        static_overrides={"scroll_area": _horizontal_container},
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
