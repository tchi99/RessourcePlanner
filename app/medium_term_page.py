from __future__ import annotations

from collections.abc import Callable
from typing import Any


MediumTermRenderer = Callable[[Any], None]
_registered_renderer: MediumTermRenderer | None = None


def register_medium_term_renderer(renderer: MediumTermRenderer) -> None:
    """Register the current medium-term renderer behind an explicit page boundary."""

    if not callable(renderer):
        raise TypeError("Le renderer moyen terme doit être appelable.")
    global _registered_renderer
    _registered_renderer = renderer


class MediumTermPage:
    """Explicit page boundary for the medium-term planning view."""

    def __init__(self, owner: Any, renderer: MediumTermRenderer) -> None:
        if not callable(renderer):
            raise TypeError("Le renderer moyen terme doit être appelable.")
        self.owner = owner
        self._renderer = renderer

    def render(self) -> None:
        self._renderer(self.owner)


def install_medium_term_page() -> None:
    """Make the explicit page authoritative after legacy composition has completed."""

    from . import ui as ui_module

    if getattr(ui_module.PlannerUI, "_medium_term_page_installed", False):
        return

    renderer = _registered_renderer
    if not callable(renderer):
        raise RuntimeError("Aucun renderer moyen terme n'est enregistré.")

    if not any(item[0] == "medium_term" for item in ui_module.NAV_ITEMS):
        planning_index = next(
            (
                index
                for index, item in enumerate(ui_module.NAV_ITEMS)
                if item[0] == "planning"
            ),
            1,
        )
        ui_module.NAV_ITEMS.insert(
            planning_index,
            ("medium_term", "timeline", "Planification moyen terme"),
        )

    previous_render_content = ui_module.PlannerUI._render_content
    previous_page_sheets = ui_module.PlannerUI._page_sheets

    def render_content(self: Any) -> None:
        if self.current_page == "medium_term":
            page = getattr(self, "medium_term_page", None)
            if page is None:
                page = MediumTermPage(self, renderer)
                self.medium_term_page = page
            page.render()
            return
        previous_render_content(self)

    def page_sheets(self: Any) -> list[str]:
        if self.current_page == "medium_term":
            return [
                "Liste_Effort",
                "DemandesMO",
                "SegmentsMO",
                "AllocationsMO",
                "Disponibilites",
                "RessourcesMO",
            ]
        return previous_page_sheets(self)

    ui_module.PlannerUI._render_content = render_content
    ui_module.PlannerUI._page_sheets = page_sheets
    ui_module.PlannerUI._medium_term_renderer = renderer
    ui_module.PlannerUI._medium_term_page_installed = True
