from __future__ import annotations

from collections.abc import Callable
from typing import Any


PlanningRenderer = Callable[[Any], None]


class OperationalPlanningPage:
    """Explicit page boundary for the operational planning view.

    The validated V1.8 renderer is still historical, but it is captured once by the
    composition root and injected into this page. PlannerUI therefore no longer needs
    to resolve a repeatedly monkey-patched ``render_planning`` method while serving a
    request. The renderer can be replaced behind this boundary in later extraction
    tranches without changing navigation or the UI shell again.
    """

    def __init__(self, owner: Any, renderer: PlanningRenderer) -> None:
        if not callable(renderer):
            raise TypeError("Le renderer du planning opérationnel doit être appelable.")
        self.owner = owner
        self._renderer = renderer

    def render(self) -> None:
        self._renderer(self.owner)


def install_operational_planning_page() -> None:
    """Capture the final composed legacy renderer behind the explicit page boundary."""
    from . import ui as ui_module

    if getattr(ui_module.PlannerUI, "_operational_planning_page_installed", False):
        return

    renderer = getattr(ui_module.PlannerUI, "render_planning", None)
    if not callable(renderer):
        raise RuntimeError("Aucun renderer de planning opérationnel n'est installé.")

    ui_module.PlannerUI._operational_planning_renderer = renderer
    ui_module.PlannerUI._operational_planning_page_installed = True
