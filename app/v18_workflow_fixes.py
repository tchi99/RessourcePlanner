from __future__ import annotations

from typing import Any

from nicegui import ui

from . import v13, v14, v15_refinements, v16
from .ui_context import ensure_scoped_ui


def _install_skill_class_precedence() -> None:
    """Prefer an explicit installation label over the generic automation keyword.

    Configuration values such as ``Installation automatisation`` contain both
    ``installation`` and ``automatis...``. The original classifier checked the
    automation keyword first and therefore mapped those skills to Programmation.
    An explicit installation wording is more specific and must win.
    """
    if getattr(v16, "_v18_skill_class_precedence_installed", False):
        return

    original_normalize = v16._normalize_resource_class

    def normalize_resource_class(value: Any) -> str | None:
        text = v16._normalized_text(value)
        if "installation" in text or "installateur" in text:
            return "Installation"
        return original_normalize(value)

    v16._normalize_resource_class = normalize_resource_class
    v16._v18_skill_class_precedence_installed = True


def _open_parent_demand(self: Any, number: str) -> None:
    demand = next(
        (
            row
            for row in self.repo.demands()
            if str(row.get("NoDemande") or "") == str(number)
        ),
        None,
    )
    if not demand:
        ui.notify("Demande associée introuvable.", type="warning")
        return
    self.open_edit_request_dialog(demand)


def _install_segment_parent_navigation() -> None:
    """Add an open-parent icon to the Demand field of an existing segment dialog."""
    if getattr(v15_refinements, "_v18_parent_navigation_installed", False):
        return

    original_segment_dialog = v15_refinements._segment_dialog
    scoped_ui = ensure_scoped_ui(
        v15_refinements,
        scope_name="segment_dialog",
        scoped_factories=("select",),
    )

    def segment_dialog(
        self: Any,
        segment: dict[str, Any] | None = None,
        demand_number: str | None = None,
    ) -> None:
        if not segment:
            original_segment_dialog(self, segment=segment, demand_number=demand_number)
            return

        parent_number = str(segment.get("NoDemande") or demand_number or "")
        original_select = scoped_ui.base_factory("select")

        def select_with_parent_link(*args: Any, **kwargs: Any) -> Any:
            component = original_select(*args, **kwargs)
            label = str(kwargs.get("label") or "")
            if label == "Demande MO" and parent_number:
                component.props("append-icon=open_in_new")
                component.on(
                    "click:append",
                    lambda _event: _open_parent_demand(self, parent_number),
                )
                component.tooltip("Ouvrir et modifier la demande associée")
            return component

        with scoped_ui.override_factory("select", select_with_parent_link):
            original_segment_dialog(
                self, segment=segment, demand_number=demand_number
            )

    v15_refinements._segment_dialog = segment_dialog
    v13._open_segment_dialog = segment_dialog
    v14._open_segment_dialog_v14 = segment_dialog
    v15_refinements._v18_parent_navigation_installed = True


def install_v18_workflow_fixes() -> None:
    _install_skill_class_precedence()
    _install_segment_parent_navigation()
