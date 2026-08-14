from __future__ import annotations

from nicegui import ui

from . import ui as ui_module


def install_v18_calendar_sizing() -> None:
    """Restore the original V1.7 operational calendar dimensions.

    V1.8 keeps the single-scroll container, but does not otherwise enlarge the
    operational planning grid.
    """
    if getattr(ui_module.PlannerUI, "_v18_calendar_sizing_installed", False):
        return

    ui.add_css(
        """
        .schedule-grid {
          grid-template-columns: repeat(8, minmax(0, 1fr)) !important;
          min-width: 1180px !important;
        }
        """
    )

    ui_module.PlannerUI._v18_calendar_sizing_installed = True
