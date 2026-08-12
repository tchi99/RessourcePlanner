from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from nicegui import ui


def _shared_by_default(function: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap a NiceGUI asset helper so calls are compatible with ui.page.

    Recent NiceGUI versions reject global/page-ambiguous calls to add_head_html,
    add_body_html and add_css when ui.page is used unless shared=True is explicit.
    RessourcePlanner's CSS/HTML assets are application-wide, so making them shared is
    the intended behavior and avoids coupling every historical feature module to a
    particular NiceGUI version.
    """

    @wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        kwargs.setdefault("shared", True)
        return function(*args, **kwargs)

    return wrapper


def install_v172_nicegui_compat() -> None:
    if getattr(ui, "_ressourceplanner_shared_assets_installed", False):
        return

    ui.add_head_html = _shared_by_default(ui.add_head_html)
    ui.add_body_html = _shared_by_default(ui.add_body_html)
    ui.add_css = _shared_by_default(ui.add_css)
    ui._ressourceplanner_shared_assets_installed = True
