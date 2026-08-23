from __future__ import annotations

from typing import Any

from nicegui import ui

from .segment_editor_compat import open_segment_editor
from .segment_repository import number, segment_records


class SegmentsPage:
    """Explicit SegmentsMO page.

    Rendering, filtering and navigation state live here instead of in v13.py. The
    editor itself remains behind a narrow compatibility adapter until its dedicated
    extraction tranche.
    """

    def __init__(self, owner: Any) -> None:
        self.owner = owner
        self.request_filter: str | None = None

    def render(self) -> None:
        rows = segment_records(self.owner.repo)
        if self.request_filter:
            rows = [
                row
                for row in rows
                if str(row.get("NoDemande") or "") == self.request_filter
            ]

        with ui.row().classes("w-full items-center"):
            with ui.column().classes("gap-0"):
                ui.label("Segments de planification").classes("text-2xl font-bold")
                subtitle = (
                    f"Demande {self.request_filter}"
                    if self.request_filter
                    else "Découpage opérationnel des demandes MO"
                )
                ui.label(subtitle).classes("muted")
            ui.space()
            if self.request_filter:
                ui.button(
                    "Toutes les demandes",
                    icon="clear_all",
                    on_click=self.clear_filter,
                ).props("flat no-caps")
            ui.button(
                "Nouveau segment",
                icon="add",
                on_click=lambda: open_segment_editor(
                    self.owner,
                    demand_number=self.request_filter,
                ),
            ).props("unelevated no-caps color=primary")

        total_hours = sum(
            number(row.get("HeuresPrevues"))
            for row in rows
            if str(row.get("Statut") or "") != "Annulé"
        )
        with ui.row().classes("w-full gap-3"):
            ui.label(f"{len(rows)} segment(s)").classes("text-sm muted")
            ui.label(f"{total_hours:g} h planifiées").classes("text-sm muted")
            ui.label("Clique une ligne pour la modifier.").classes("text-sm muted")

        grid_rows = [
            {
                "IDSegment": row.get("IDSegment"),
                "NoDemande": row.get("NoDemande"),
                "Projet": (
                    f"{row.get('NumeroProjet') or '—'} · "
                    f"{row.get('NomProjet') or ''}"
                ),
                "Technicien": row.get("Technicien") or "",
                "Début": self.owner._date_text(row.get("DateDebut")),
                "Fin": self.owner._date_text(row.get("DateFin")),
                "Heures": number(row.get("HeuresPrevues")),
                "Statut": row.get("Statut") or "",
                "Description": row.get("Description") or "",
            }
            for row in rows
        ]
        grid = ui.aggrid(
            {
                "columnDefs": [
                    {
                        "headerName": "Segment",
                        "field": "IDSegment",
                        "minWidth": 145,
                        "pinned": "left",
                    },
                    {"headerName": "Demande", "field": "NoDemande", "minWidth": 145},
                    {"headerName": "Projet", "field": "Projet", "minWidth": 230},
                    {
                        "headerName": "Technicien",
                        "field": "Technicien",
                        "minWidth": 160,
                    },
                    {"headerName": "Début", "field": "Début", "minWidth": 115},
                    {"headerName": "Fin", "field": "Fin", "minWidth": 115},
                    {"headerName": "Heures", "field": "Heures", "minWidth": 90},
                    {"headerName": "Statut", "field": "Statut", "minWidth": 115},
                    {
                        "headerName": "Description",
                        "field": "Description",
                        "minWidth": 240,
                    },
                ],
                "rowData": grid_rows,
                "defaultColDef": {
                    "sortable": True,
                    "filter": True,
                    "resizable": True,
                },
                "animateRows": True,
            }
        ).classes("w-full h-[520px]")

        def row_click(event: Any) -> None:
            args = event.args if isinstance(event.args, dict) else {}
            identifier = (args.get("data") or {}).get("IDSegment")
            segment = next(
                (
                    row
                    for row in segment_records(self.owner.repo)
                    if row.get("IDSegment") == identifier
                ),
                None,
            )
            if segment:
                open_segment_editor(self.owner, segment=segment)

        grid.on("cellClicked", row_click)

    def clear_filter(self) -> None:
        self.request_filter = None
        self.owner.render_content.refresh()

    def open_for_demand(self, demand: dict[str, Any]) -> None:
        self.request_filter = str(demand.get("NoDemande") or "")
        self.owner.current_page = "segments"
        self.owner.selected_request = None
        self.owner._signature = self.owner._signature_for_current_page()
        self.owner.render_content.refresh()
