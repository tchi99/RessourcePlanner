from __future__ import annotations

from typing import Any

from nicegui import ui

from .application.runtime_services import demand_service
from . import ui as ui_module


def _open_approval_dialog_via_service(
    self: ui_module.PlannerUI,
    demand: dict[str, Any],
) -> None:
    """Transitional approval dialog backed by the explicit DemandService."""
    self.interaction_lock = True

    with ui.dialog() as dialog, ui.card().classes("w-[560px] max-w-full"):
        ui.label(f"Approuver {demand.get('NoDemande')}").classes("text-xl font-bold")
        ui.label(
            f"{demand.get('NumeroProjet') or '—'} · {demand.get('NomProjet') or ''}"
        )

        comment = ui.textarea("Commentaire d'approbation").classes("w-full")

        def approve() -> None:
            try:
                demand_service(self.repo).approve(
                    str(demand["NoDemande"]),
                    str(comment.value or ""),
                )
                dialog.close()
                self._after_write("Demande approuvée")
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        with ui.row().classes("w-full justify-end"):
            ui.button("Annuler", on_click=dialog.close).props("flat no-caps")
            ui.button("Approuver", icon="check", on_click=approve).props(
                "unelevated no-caps color=positive"
            )

    dialog.on("hide", lambda _: self._unlock())
    dialog.open()


def install_demand_service_ui() -> None:
    """Bind approval UI to DemandService until request pages are extracted.

    The V1.x request page still lives on ``PlannerUI``. This explicit composition-time
    binding makes the user workflow cross the application-service boundary now; tranche
    4 can delete it when the request page/dialog becomes a dedicated UI module.
    """
    if getattr(ui_module.PlannerUI, "_demand_service_ui_installed", False):
        return

    ui_module.PlannerUI.open_approval_dialog = _open_approval_dialog_via_service
    ui_module.PlannerUI._demand_service_ui_installed = True
