from __future__ import annotations

from typing import Any

from nicegui import ui as nicegui_ui

from . import v16, v17
from .ui_context import ensure_scoped_ui


def _horizontal_container(*args: Any, **kwargs: Any) -> Any:
    del args, kwargs
    return nicegui_ui.element("div").classes("v18-operational-scroll")


def install_v18_single_scroll() -> None:
    """Make legacy operational UI overrides module-local and concurrency-safe.

    V1.8 needs a normal horizontal overflow container instead of the old Quasar
    ``scroll_area``.  In addition, the V1.6/V1.7 refinement renderers still perform
    temporary assignments to their module's ``ui.select`` factory.  Both modules now
    receive a :class:`ScopedNiceGUI` facade before any page render occurs, so those
    historical assignments are stored in a task/client-local ``ContextVar`` rather
    than mutating process-wide ``nicegui.ui``.

    The historical renderer code can therefore remain behavior-compatible until it is
    moved into explicit pages later in #15, without exposing concurrent clients to one
    another's temporary UI factory overrides.
    """
    if getattr(v17, "_v18_single_scroll_installed", False):
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
