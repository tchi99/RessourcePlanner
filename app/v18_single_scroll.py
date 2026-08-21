from __future__ import annotations

from typing import Any

from nicegui import ui as nicegui_ui

from . import v17


class _OperationalPlanningUI:
    """Module-local NiceGUI facade for the V1.7 operational renderer.

    The historical renderer calls ``v17.ui.scroll_area()`` for its outer calendar
    container.  V1.8 needs a normal overflow-x div instead, but mutating
    ``nicegui.ui.scroll_area`` while a page is rendering is unsafe once multiple
    clients can render concurrently.  This facade changes only the dependency seen by
    ``app.v17`` and delegates every other UI factory to the real NiceGUI module.
    """

    _v18_operational_facade = True

    def __init__(self, delegate: Any) -> None:
        self._delegate = delegate

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)

    def scroll_area(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        return self._delegate.element("div").classes("v18-operational-scroll")


def install_v18_single_scroll() -> None:
    """Use one horizontal scrollbar without mutating global NiceGUI factories.

    ``app.v17`` remains a historical renderer for now, so this tranche keeps its
    public behavior while replacing the previous render-time save/replace/restore of
    ``nicegui.ui.scroll_area`` with an immutable module-local adapter.  A later #15
    tranche can move the renderer itself into ``ui/pages`` and use the explicit div
    directly; no global UI mutation will be required in the meantime.
    """
    if getattr(v17, "_v18_single_scroll_installed", False):
        return

    current_ui = v17.ui
    if not getattr(current_ui, "_v18_operational_facade", False):
        v17.ui = _OperationalPlanningUI(current_ui)

    nicegui_ui.add_css(
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

    v17._v18_single_scroll_installed = True
