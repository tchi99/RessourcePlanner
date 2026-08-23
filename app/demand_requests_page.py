from __future__ import annotations

from typing import Any

from nicegui import ui

from .application.runtime_services import demand_service
from .segment_repository import number, segment_records






class DemandRequestsPage:
    """Explicit Demandes / approbations page.

    Lifecycle mutations cross DemandService directly. The page owns its dialogs and
    selection rendering; PlannerUI only delegates navigation/rendering to this object.
    """

    def __init__(self, owner: Any) -> None:
        self.owner = owner
        self.request_actions = ui.refreshable(self._render_actions)

    def render(self) -> None:
        demands = self.owner.repo.demands()
        demand_rows = [self._grid_row(demand) for demand in reversed(demands)]
        columns = [
            {
                "headerName": "N° demande",
                "field": "NoDemande",
                "minWidth": 150,
                "pinned": "left",
            },
            {"headerName": "Projet", "field": "Projet", "minWidth": 210},
            {"headerName": "Client", "field": "Client", "minWidth": 150},
            {"headerName": "Priorité", "field": "Priorite", "minWidth": 110},
            {
                "headerName": "Début souhaité",
                "field": "Debut",
                "minWidth": 135,
            },
            {
                "headerName": "Fin souhaitée",
                "field": "Fin",
                "minWidth": 135,
            },
            {"headerName": "Statut", "field": "Statut", "minWidth": 145},
            {"headerName": "Demandeur", "field": "Demandeur", "minWidth": 150},
        ]

        with ui.row().classes("w-full items-center"):
            with ui.column().classes("gap-0"):
                ui.label("Demandes / approbations").classes("text-2xl font-bold")
                ui.label("Clique une ligne pour afficher les actions.").classes("muted")
            ui.space()
            ui.button(
                "Nouvelle demande",
                icon="add",
                on_click=self.owner.open_new_request_dialog,
            ).props("unelevated no-caps color=primary")

        grid = ui.aggrid(
            {
                "columnDefs": columns,
                "rowData": demand_rows,
                "defaultColDef": {
                    "sortable": True,
                    "filter": True,
                    "resizable": True,
                },
                "animateRows": True,
            }
        ).classes("w-full h-[430px]")

        def select_request(event: Any) -> None:
            args = event.args if isinstance(event.args, dict) else {}
            self.owner.selected_request = (args.get("data") or {}).get("NoDemande")
            self.request_actions.refresh()

        grid.on("cellClicked", select_request)
        self.request_actions()

    def _render_actions(self) -> None:
        if not self.owner.selected_request:
            with ui.card().classes("section-card w-full"):
                ui.label("Aucune demande sélectionnée").classes("muted")
            return

        demand = next(
            (
                row
                for row in self.owner.repo.demands()
                if str(row.get("NoDemande") or "")
                == str(self.owner.selected_request)
            ),
            None,
        )
        if not demand:
            return

        status = str(demand.get("Statut") or "")
        related_segments = [
            segment
            for segment in segment_records(self.owner.repo)
            if str(segment.get("NoDemande") or "")
            == str(demand.get("NoDemande") or "")
            and str(segment.get("Statut") or "") != "Annulé"
        ]
        planned_hours = sum(
            number(segment.get("HeuresPrevues")) for segment in related_segments
        )

        with ui.card().classes("section-card w-full"):
            with ui.row().classes("w-full items-center"):
                with ui.column().classes("gap-0"):
                    ui.label(str(demand.get("NoDemande") or "")).classes(
                        "text-lg font-bold"
                    )
                    ui.label(
                        f"{demand.get('NumeroProjet') or '—'} · "
                        f"{demand.get('NomProjet') or ''}"
                    ).classes("text-sm")
                    ui.label(str(demand.get("Description") or "")).classes(
                        "text-sm muted"
                    )
                    if related_segments:
                        ui.label(
                            f"{len(related_segments)} segment(s) · "
                            f"{planned_hours:g} h détaillées"
                        ).classes("text-xs text-blue-700")
                ui.space()
                ui.label(status).classes("status-pill bg-blue-50 text-blue-800")

            with ui.row().classes("w-full mt-3"):
                if status in {"Brouillon", "À corriger"}:
                    ui.button(
                        "Soumettre",
                        icon="send",
                        on_click=lambda: self._submit(demand),
                    ).props("outline no-caps")

                if status == "Soumise":
                    ui.button(
                        "Approuver",
                        icon="check_circle",
                        on_click=lambda: self._open_approval_dialog(demand),
                    ).props("unelevated no-caps color=positive")
                    ui.button(
                        "À corriger",
                        icon="edit_note",
                        on_click=lambda: self._open_correction_dialog(demand),
                    ).props("outline no-caps color=warning")

                if status == "En planification":
                    ui.button(
                        "Gérer les segments",
                        icon="view_timeline",
                        on_click=lambda: self._go_to_segments(demand),
                    ).props("unelevated no-caps color=primary")

                if status not in {"Annulée", "Fermé"}:
                    ui.button(
                        "Modifier la demande",
                        icon="edit",
                        on_click=lambda: self.owner.open_edit_request_dialog(demand),
                    ).props("outline no-caps")
                    ui.button(
                        "Annuler",
                        icon="cancel",
                        on_click=lambda: self._cancel(demand),
                    ).props("flat no-caps color=negative")

    def _submit(self, demand: dict[str, Any]) -> None:
        try:
            demand_service(self.owner.repo).submit(str(demand["NoDemande"]))
            self.owner._after_write("Demande soumise pour approbation")
        except Exception as exc:
            ui.notify(str(exc), type="negative")

    def _cancel(self, demand: dict[str, Any]) -> None:
        try:
            demand_service(self.owner.repo).cancel(str(demand["NoDemande"]))
            self.owner._after_write("Demande annulée")
        except Exception as exc:
            ui.notify(str(exc), type="negative")

    def _open_approval_dialog(self, demand: dict[str, Any]) -> None:
        self.owner.interaction_lock = True

        with ui.dialog() as dialog, ui.card().classes("w-[560px] max-w-full"):
            ui.label(f"Approuver {demand.get('NoDemande')}").classes(
                "text-xl font-bold"
            )
            ui.label(
                f"{demand.get('NumeroProjet') or '—'} · "
                f"{demand.get('NomProjet') or ''}"
            )
            comment = ui.textarea("Commentaire d'approbation").classes("w-full")

            def approve() -> None:
                try:
                    demand_service(self.owner.repo).approve(
                        str(demand["NoDemande"]),
                        str(comment.value or ""),
                    )
                    dialog.close()
                    self.owner._after_write("Demande approuvée")
                except Exception as exc:
                    ui.notify(str(exc), type="negative")

            with ui.row().classes("w-full justify-end"):
                ui.button("Annuler", on_click=dialog.close).props("flat no-caps")
                ui.button("Approuver", icon="check", on_click=approve).props(
                    "unelevated no-caps color=positive"
                )

        dialog.on("hide", lambda _: self.owner._unlock())
        dialog.open()

    def _open_correction_dialog(self, demand: dict[str, Any]) -> None:
        self.owner.interaction_lock = True

        with ui.dialog() as dialog, ui.card().classes("w-[560px] max-w-full"):
            ui.label(
                f"Retourner {demand.get('NoDemande')} pour correction"
            ).classes("text-xl font-bold")
            comment = ui.textarea("Correction demandée").classes("w-full")

            def send_back() -> None:
                try:
                    demand_service(self.owner.repo).request_correction(
                        str(demand["NoDemande"]),
                        str(comment.value or ""),
                    )
                    dialog.close()
                    self.owner._after_write("Demande retournée pour correction")
                except ValueError as exc:
                    ui.notify(str(exc), type="warning")
                except Exception as exc:
                    ui.notify(str(exc), type="negative")

            with ui.row().classes("w-full justify-end"):
                ui.button("Annuler", on_click=dialog.close).props("flat no-caps")
                ui.button("Envoyer", icon="reply", on_click=send_back).props(
                    "unelevated no-caps color=warning"
                )

        dialog.on("hide", lambda _: self.owner._unlock())
        dialog.open()

    def _go_to_segments(self, demand: dict[str, Any]) -> None:
        self.owner.segments_page.open_for_demand(demand)

    def _grid_row(self, demand: dict[str, Any]) -> dict[str, Any]:
        return {
            "NoDemande": demand.get("NoDemande"),
            "Projet": (
                f"{demand.get('NumeroProjet') or '—'} · "
                f"{demand.get('NomProjet') or ''}"
            ),
            "Client": demand.get("Client") or "",
            "Priorite": demand.get("Priorite") or "",
            "Debut": self.owner._date_text(demand.get("DateDebutSouhaitee")),
            "Fin": self.owner._date_text(demand.get("DateFinSouhaitee")),
            "Statut": demand.get("Statut") or "",
            "Demandeur": demand.get("Demandeur") or "",
        }
