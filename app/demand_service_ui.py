from __future__ import annotations

from typing import Any

from nicegui import ui

from . import ui as ui_module
from .application.runtime_services import demand_service


def _submit_request_via_service(
    self: ui_module.PlannerUI,
    demand: dict[str, Any],
) -> None:
    try:
        demand_service(self.repo).submit(str(demand["NoDemande"]))
        self._after_write("Demande soumise pour approbation")
    except Exception as exc:
        ui.notify(str(exc), type="negative")


def _cancel_request_via_service(
    self: ui_module.PlannerUI,
    demand: dict[str, Any],
) -> None:
    try:
        demand_service(self.repo).cancel(str(demand["NoDemande"]))
        self._after_write("Demande annulée")
    except Exception as exc:
        ui.notify(str(exc), type="negative")


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


def _open_correction_dialog_via_service(
    self: ui_module.PlannerUI,
    demand: dict[str, Any],
) -> None:
    self.interaction_lock = True

    with ui.dialog() as dialog, ui.card().classes("w-[560px] max-w-full"):
        ui.label(
            f"Retourner {demand.get('NoDemande')} pour correction"
        ).classes("text-xl font-bold")

        comment = ui.textarea("Correction demandée").classes("w-full")

        def send_back() -> None:
            try:
                demand_service(self.repo).request_correction(
                    str(demand["NoDemande"]),
                    str(comment.value or ""),
                )
                dialog.close()
                self._after_write("Demande retournée pour correction")
            except ValueError as exc:
                ui.notify(str(exc), type="warning")
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        with ui.row().classes("w-full justify-end"):
            ui.button("Annuler", on_click=dialog.close).props("flat no-caps")
            ui.button("Envoyer", icon="reply", on_click=send_back).props(
                "unelevated no-caps color=warning"
            )

    dialog.on("hide", lambda _: self._unlock())
    dialog.open()


def install_demand_service_ui() -> None:
    """Install explicit demand lifecycle actions on the current request page.

    ``PlannerUI`` no longer carries dormant V1.1 implementations of these actions.
    Until the whole request page is extracted, this module is the sole UI owner of
    submit/approve/correction/cancel and routes every mutation through ``DemandService``.
    """
    if getattr(ui_module.PlannerUI, "_demand_service_ui_installed", False):
        return

    ui_module.PlannerUI.submit_request = _submit_request_via_service
    ui_module.PlannerUI.cancel_request = _cancel_request_via_service
    ui_module.PlannerUI.open_approval_dialog = _open_approval_dialog_via_service
    ui_module.PlannerUI.open_correction_dialog = _open_correction_dialog_via_service
    ui_module.PlannerUI._demand_service_ui_installed = True
