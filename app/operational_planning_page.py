from __future__ import annotations

from collections.abc import Callable
from typing import Any


PlanningRenderer = Callable[[Any], None]
_registered_renderer: PlanningRenderer | None = None


def register_operational_planning_renderer(renderer: PlanningRenderer) -> None:
    """Register the renderer selected by the legacy composition stack.

    Versioned installers may still decide which validated renderer is authoritative,
    but they no longer need to replace ``PlannerUI.render_planning`` on the class.
    The explicit page installer consumes this registration once after legacy
    composition is complete.
    """
    if not callable(renderer):
        raise TypeError("Le renderer du planning opérationnel doit être appelable.")
    global _registered_renderer
    _registered_renderer = renderer


class OperationalPlanningPage:
    """Explicit page boundary for the operational planning view.

    The validated V1.8 renderer is injected once after runtime composition. PlannerUI
    routes navigation to this object and no longer needs a final renderer monkey-patch
    on its class. The implementation can therefore move out of versioned modules
    incrementally without changing the shell again.
    """

    def __init__(self, owner: Any, renderer: PlanningRenderer) -> None:
        if not callable(renderer):
            raise TypeError("Le renderer du planning opérationnel doit être appelable.")
        self.owner = owner
        self._renderer = renderer

    def render(self) -> None:
        self._renderer(self.owner)


def install_operational_planning_page() -> None:
    """Publish the explicitly registered final renderer to future PlannerUI instances."""
    from . import ui as ui_module

    if getattr(ui_module.PlannerUI, "_operational_planning_page_installed", False):
        return

    renderer = _registered_renderer
    if not callable(renderer):
        # Transitional fallback for earlier V1 installers. The final V1.8 stack now
        # registers explicitly, but keeping this fallback makes partial/test
        # compositions fail gracefully while older layers are extracted.
        renderer = getattr(ui_module.PlannerUI, "render_planning", None)
    if not callable(renderer):
        raise RuntimeError("Aucun renderer de planning opérationnel n'est installé.")

    ui_module.PlannerUI._operational_planning_renderer = renderer
    ui_module.PlannerUI._operational_planning_page_installed = True
