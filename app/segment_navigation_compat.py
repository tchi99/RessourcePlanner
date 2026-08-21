from __future__ import annotations

from typing import Any

from nicegui import ui

from . import v13, v14, v15_refinements
from .ui_context import ensure_scoped_ui


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


def install_segment_navigation_compat() -> None:
    """Add the parent-demand action to the historical segment dialog safely.

    The segment renderer still lives in ``v15_refinements``. Until that dialog is
    extracted into an explicit page, a scoped ``select`` factory decorates only the
    Demand field with the open-parent icon without mutating process-wide NiceGUI state.
    """
    if getattr(v15_refinements, "_parent_navigation_installed", False):
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
    v15_refinements._parent_navigation_installed = True
