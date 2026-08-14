from __future__ import annotations

from typing import Any

from nicegui import ui

from . import ui as ui_module


def install_v18_single_scroll() -> None:
    """Use one horizontal scrollbar for the operational planning calendar.

    The V1.7 renderer wraps the complete operational calendar in a Quasar
    ``ui.scroll_area`` while the page itself can also scroll. With a wide schedule
    grid this can expose two independent scrollbars. For the V1.8 UI we keep the
    existing renderer and replace only that scroll-area container, during the
    synchronous render, with a normal overflow-x div. Vertical navigation is then
    handled by the page and horizontal navigation by the calendar container, which
    matches the medium-term planning behavior.
    """
    if getattr(ui_module.PlannerUI, "_v18_single_scroll_installed", False):
        return

    original_render_planning = ui_module.PlannerUI.render_planning

    def render_planning(self: ui_module.PlannerUI) -> Any:
        original_scroll_area = ui.scroll_area

        def horizontal_container(*args: Any, **kwargs: Any):
            del args, kwargs
            return ui.element("div").classes("v18-operational-scroll")

        ui.scroll_area = horizontal_container
        try:
            return original_render_planning(self)
        finally:
            ui.scroll_area = original_scroll_area

    ui.add_css(
        """
        .v18-operational-scroll {
          width: 100%;
          height: auto !important;
          max-height: none !important;
          overflow-x: auto;
          overflow-y: visible;
          overscroll-behavior-x: contain;
        }
        """
    )

    ui_module.PlannerUI.render_planning = render_planning
    ui_module.PlannerUI._v18_single_scroll_installed = True
