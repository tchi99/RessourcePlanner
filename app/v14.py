from __future__ import annotations

from datetime import date
from typing import Any

from nicegui import ui

from . import features
from . import ui as ui_module
from . import v13
from .bugfixes import schedulable_technicians
from .excel_repository import ExcelRepository, MASTER_SHEETS, _date_from_any
from .services import week_days, week_start
from .v14_engine import (
    ALLOCATION_SHEET,
    PLAN_TYPES,
    PRIORITIES,
    SEGMENT_EXTRA_HEADERS,
    allocated_by_segment,
    allocation_records,
    demand_lookup,
    ensure_v14_sheets,
    rebuild_allocations,
    segment_competence,
    segment_plan_type,
    segment_priority,
    weekly_allocation_load,
)


def _open_segment_dialog_v14(
    self: ui_module.PlannerUI,
    segment: dict[str, Any] | None = None,
    demand_number: str | None = None,
) -> None:
    self.interaction_lock = True
    editing = segment is not None
    demands = {str(row.get("NoDemande") or ""): row for row in self.repo.demands()}
    selected_number = str(segment.get("NoDemande") or "") if segment else str(demand_number or "")
    demand_options = v13._demand_options(self.repo)
    if selected_number and selected_number not in demand_options:
        demand = demands.get(selected_number, {})
        demand_options[selected_number] = (
            f"{selected_number} — {demand.get('NumeroProjet') or '—'} · {demand.get('NomProjet') or ''}"
        )

    current_demand = demands.get(selected_number, {})
    tech_options = [row["name"] for row in schedulable_technicians(self.repo)]
    competence_options = list(self.repo.competencies())
    effort_options = v13._effort_options(
        self.repo,
        current_demand.get("NumeroProjet") if current_demand else None,
    )
    inherited_source = v13._source_effort_for_demand(current_demand) if current_demand else None

    source_value = inherited_source
    if segment and segment.get("SourceEffortRow") not in (None, ""):
        try:
            source_value = str(int(float(segment.get("SourceEffortRow"))))
        except (TypeError, ValueError):
            source_value = str(segment.get("SourceEffortRow"))
    if source_value and source_value not in effort_options:
        effort_options.update(v13._effort_options(self.repo))

    initial_competence = (
        str(segment.get("CompetenceRequise") or "")
        if segment
        else str(current_demand.get("CompetencesRequises") or "")
    ) or None
    if initial_competence and initial_competence not in competence_options:
        competence_options.append(initial_competence)

    initial_tech = (
        str(segment.get("Technicien") or "")
        if segment
        else str(current_demand.get("TechnicienPropose") or "")
    )
    initial_tech = initial_tech if initial_tech in tech_options else None
    initial_type = segment_plan_type(segment or {})

    with ui.dialog() as dialog, ui.card().classes("w-[820px] max-w-full"):
        ui.label(
            f"Modifier {segment.get('IDSegment')}" if editing else "Nouveau segment"
        ).classes("text-xl font-bold")
        ui.label(
            "Le technicien est facultatif. Sans technicien, le segment reste dans « Travaux à planifier »."
        ).classes("text-xs muted")

        demand_select = ui.select(
            demand_options,
            label="Demande MO",
            value=selected_number or None,
            with_input=True,
            clearable=False,
        ).classes("w-full")
        if selected_number:
            demand_select.props("readonly")

        with ui.row().classes("w-full"):
            technician = ui.select(
                tech_options,
                label="Technicien (optionnel)",
                value=initial_tech,
                with_input=True,
                clearable=True,
            ).classes("flex-1")
            competence = ui.select(
                competence_options,
                label="Compétence requise",
                value=initial_competence,
                with_input=True,
                clearable=True,
            ).classes("flex-1")

        with ui.row().classes("w-full"):
            planning_type = ui.select(
                PLAN_TYPES,
                label="Type de planification",
                value=initial_type,
            ).classes("flex-1")
            priority = ui.select(
                PRIORITIES,
                label="Priorité",
                value=(
                    str(segment.get("Priorite") or "")
                    if segment
                    else str(current_demand.get("Priorite") or "Normale")
                ) or "Normale",
            ).classes("flex-1")
            status = ui.select(
                v13.SEGMENT_STATUSES,
                label="Statut",
                value=(
                    str(segment.get("Statut") or "")
                    if segment
                    else ("Planifié" if initial_tech else "À assigner")
                ) or "À assigner",
            ).classes("flex-1")

        with ui.row().classes("w-full"):
            start = ui.input(
                "Début",
                value=self._date_text(segment.get("DateDebut")) if segment else self._date_text(
                    current_demand.get("DateDebutSouhaitee")
                ),
            ).props("type=date").classes("flex-1")
            end = ui.input(
                "Fin",
                value=self._date_text(segment.get("DateFin")) if segment else self._date_text(
                    current_demand.get("DateFinSouhaitee")
                ),
            ).props("type=date").classes("flex-1")
            hours = ui.number(
                "Heures prévues",
                value=(
                    v13._number(segment.get("HeuresPrevues"))
                    if segment
                    else v13._number(current_demand.get("TempsEstimeHeures")) or None
                ),
                min=0.5,
                step=0.5,
            ).classes("flex-1")

        source = ui.select(
            effort_options,
            label="Planification moyen terme liée (optionnel)",
            value=source_value,
            with_input=True,
            clearable=True,
        ).classes("w-full")
        description = ui.input(
            "Description / précision",
            value=str(segment.get("Description") or "") if segment else str(
                current_demand.get("Description") or ""
            ),
        ).classes("w-full")

        def get_demand() -> dict[str, Any]:
            return demands.get(str(demand_select.value or ""), {})

        def validate() -> bool:
            if not demand_select.value:
                ui.notify("Sélectionne une demande.", type="warning")
                return False
            start_date = _date_from_any(start.value)
            end_date = _date_from_any(end.value) or start_date
            if not start_date:
                ui.notify("La date de début est requise.", type="warning")
                return False
            if end_date and end_date < start_date:
                ui.notify("La date de fin ne peut pas précéder la date de début.", type="warning")
                return False
            if v13._number(hours.value) <= 0:
                ui.notify("Les heures prévues doivent être supérieures à zéro.", type="warning")
                return False
            if not competence.value:
                ui.notify(
                    "La compétence requise est nécessaire pour un segment, même s'il n'est pas encore assigné.",
                    type="warning",
                )
                return False
            return True

        def payload() -> dict[str, Any]:
            demand = get_demand()
            source_row: Any = source.value
            if source_row not in (None, ""):
                try:
                    source_row = int(float(source_row))
                except (TypeError, ValueError):
                    pass
            tech = str(technician.value or "").strip()
            chosen_status = str(status.value or "")
            if not tech and chosen_status not in {"Annulé", "Terminé"}:
                chosen_status = "À assigner"
            elif tech and chosen_status == "À assigner":
                chosen_status = "Planifié"
            return {
                "NoDemande": demand_select.value,
                "NumeroProjet": demand.get("NumeroProjet"),
                "NomProjet": demand.get("NomProjet"),
                "Technicien": tech or None,
                "DateDebut": start.value,
                "DateFin": end.value or start.value,
                "HeuresPrevues": hours.value,
                "Statut": chosen_status,
                "Description": description.value,
                "SourceEffortRow": source_row,
                "CompetenceRequise": competence.value,
                "TypePlanification": planning_type.value or "Flexible",
                "Priorite": priority.value or "Normale",
            }

        def save() -> None:
            if not validate():
                return
            try:
                data = payload()
                if editing:
                    v13.update_segment(self.repo, str(segment["IDSegment"]), data)
                    message = f"{segment['IDSegment']} mis à jour"
                else:
                    ident = v13.add_segment(self.repo, data)
                    message = f"{ident} créé"
                summary = rebuild_allocations(self.repo)
                dialog.close()
                extra = (
                    f" · {summary['unallocated_hours']:g} h restent sans capacité"
                    if summary["unallocated_hours"] > 0
                    else ""
                )
                self._after_write(message + extra)
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        def cancel_segment() -> None:
            try:
                v13.update_segment(
                    self.repo,
                    str(segment["IDSegment"]),
                    {"Statut": "Annulé"},
                )
                rebuild_allocations(self.repo)
                dialog.close()
                self._after_write(f"{segment['IDSegment']} annulé")
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        with ui.row().classes("w-full justify-end"):
            ui.button("Annuler", on_click=dialog.close).props("flat no-caps")
            if editing and str(segment.get("Statut") or "") != "Annulé":
                ui.button(
                    "Annuler le segment",
                    icon="cancel",
                    on_click=cancel_segment,
                ).props("flat no-caps color=negative")
            ui.button("Enregistrer", icon="save", on_click=save).props(
                "unelevated no-caps color=primary"
            )

    dialog.on("hide", lambda _: self._unlock())
    dialog.open()


def _render_segments_v14(self: ui_module.PlannerUI) -> None:
    filter_request = getattr(self, "segment_request_filter", None)
    rows = v13.segment_records(self.repo)
    if filter_request:
        rows = [
            row for row in rows if str(row.get("NoDemande") or "") == str(filter_request)
        ]
    allocated = allocated_by_segment(self.repo)
    demands = demand_lookup(self.repo)

    with ui.row().classes("w-full items-center"):
        with ui.column().classes("gap-0"):
            ui.label("Segments de planification").classes("text-2xl font-bold")
            ui.label(
                f"Demande {filter_request}"
                if filter_request
                else "Besoins opérationnels, assignés ou à planifier"
            ).classes("muted")
        ui.space()
        if filter_request:
            ui.button(
                "Toutes les demandes",
                icon="clear_all",
                on_click=lambda: v13._clear_segment_filter(self),
            ).props("flat no-caps")
        ui.button(
            "Nouveau segment",
            icon="add",
            on_click=lambda: _open_segment_dialog_v14(self, demand_number=filter_request),
        ).props("unelevated no-caps color=primary")

    grid_rows = []
    for row in rows:
        demand = demands.get(str(row.get("NoDemande") or ""), {})
        requested = v13._number(row.get("HeuresPrevues"))
        allocated_hours = allocated.get(str(row.get("IDSegment") or ""), 0.0)
        grid_rows.append(
            {
                "IDSegment": row.get("IDSegment"),
                "NoDemande": row.get("NoDemande"),
                "Projet": f"{row.get('NumeroProjet') or '—'} · {row.get('NomProjet') or ''}",
                "Technicien": row.get("Technicien") or "À assigner",
                "Compétence": segment_competence(row, demands),
                "Type": segment_plan_type(row),
                "Priorité": segment_priority(row, demands),
                "Début": self._date_text(row.get("DateDebut")),
                "Fin": self._date_text(row.get("DateFin")),
                "Heures": requested,
                "Allouées": round(allocated_hours, 1),
                "Restantes": round(max(requested - allocated_hours, 0.0), 1),
                "Statut": row.get("Statut") or "",
                "Description": row.get("Description") or demand.get("Description") or "",
            }
        )

    grid = ui.aggrid(
        {
            "columnDefs": [
                {"headerName": "Segment", "field": "IDSegment", "minWidth": 145, "pinned": "left"},
                {"headerName": "Demande", "field": "NoDemande", "minWidth": 145},
                {"headerName": "Projet", "field": "Projet", "minWidth": 220},
                {"headerName": "Technicien", "field": "Technicien", "minWidth": 155},
                {"headerName": "Compétence", "field": "Compétence", "minWidth": 170},
                {"headerName": "Type", "field": "Type", "minWidth": 100},
                {"headerName": "Priorité", "field": "Priorité", "minWidth": 100},
                {"headerName": "Début", "field": "Début", "minWidth": 110},
                {"headerName": "Fin", "field": "Fin", "minWidth": 110},
                {"headerName": "Heures", "field": "Heures", "minWidth": 90},
                {"headerName": "Allouées", "field": "Allouées", "minWidth": 95},
                {"headerName": "Restantes", "field": "Restantes", "minWidth": 100},
                {"headerName": "Statut", "field": "Statut", "minWidth": 115},
                {"headerName": "Description", "field": "Description", "minWidth": 240},
            ],
            "rowData": grid_rows,
            "defaultColDef": {"sortable": True, "filter": True, "resizable": True},
            "animateRows": True,
        }
    ).classes("w-full h-[560px]")

    def row_click(event: Any) -> None:
        args = event.args if isinstance(event.args, dict) else {}
        ident = (args.get("data") or {}).get("IDSegment")
        segment = next(
            (
                row
                for row in v13.segment_records(self.repo)
                if str(row.get("IDSegment") or "") == str(ident)
            ),
            None,
        )
        if segment:
            _open_segment_dialog_v14(self, segment=segment)

    grid.on("cellClicked", row_click)


def _unassigned_segments(repo: ExcelRepository) -> list[dict[str, Any]]:
    return [
        row
        for row in v13.segment_records(repo, include_cancelled=False)
        if not str(row.get("Technicien") or "").strip()
        and str(row.get("Statut") or "") not in {"Annulé", "Terminé"}
    ]


def _render_operational_planning_v14(self: ui_module.PlannerUI) -> None:
    days = week_days(self.current_week)
    techs = schedulable_technicians(self.repo)
    allocations = [
        row
        for row in allocation_records(self.repo)
        if row.get("Date") and days[0] <= row["Date"] <= days[-1]
    ]
    segments = {
        str(row.get("IDSegment") or ""): row
        for row in v13.segment_records(self.repo, include_cancelled=False)
    }
    demands = demand_lookup(self.repo)
    unassigned = _unassigned_segments(self.repo)

    with ui.row().classes("w-full items-center"):
        with ui.column().classes("gap-0"):
            ui.label("Planning opérationnel").classes("text-2xl font-bold")
            ui.label(
                "Les allocations fixes réservent la capacité en premier; les segments flexibles utilisent le temps restant."
            ).classes("muted")
        ui.space()
        ui.button(
            "Recalculer",
            icon="calculate",
            on_click=lambda: _recalculate_from_ui(self),
        ).props("outline no-caps")
        ui.button(icon="chevron_left", on_click=self.previous_week).props("flat round")
        ui.button("Aujourd'hui", on_click=self.today_week).props("outline no-caps")
        ui.button(icon="chevron_right", on_click=self.next_week).props("flat round")
        ui.label(f"{days[0].strftime('%d %b')} – {days[-1].strftime('%d %b %Y')}").classes(
            "font-semibold ml-2"
        )

    if unassigned:
        with ui.card().classes("section-card w-full"):
            with ui.row().classes("w-full items-center"):
                ui.label(f"Travaux à planifier ({len(unassigned)})").classes(
                    "text-lg font-semibold"
                )
                ui.space()
                ui.label("Technicien non assigné").classes("text-xs text-orange-700")
            with ui.row().classes("w-full gap-2 flex-wrap"):
                for segment in unassigned[:12]:
                    competence = segment_competence(segment, demands) or "Compétence non précisée"
                    with ui.card().classes("p-3 min-w-[250px] max-w-[340px]"):
                        ui.label(
                            f"{segment.get('NumeroProjet') or '—'} · {segment.get('NomProjet') or ''}"
                        ).classes("text-sm font-semibold")
                        ui.label(str(segment.get("Description") or "")).classes("text-xs")
                        ui.label(
                            f"{competence} · {v13._number(segment.get('HeuresPrevues')):g} h"
                        ).classes("text-xs text-orange-700")
                        ui.label(
                            f"{self._date_text(segment.get('DateDebut'))} → {self._date_text(segment.get('DateFin'))}"
                        ).classes("text-xs muted")
                        ui.button(
                            "Planifier",
                            icon="person_add",
                            on_click=lambda s=segment: _open_segment_dialog_v14(self, segment=s),
                        ).props("flat dense no-caps")

    with ui.scroll_area().classes("w-full h-[calc(100vh-300px)]"):
        with ui.grid(columns=8).classes("schedule-grid gap-0"):
            with ui.column().classes("day-header p-3 justify-center"):
                ui.label("Ressource").classes("font-semibold")
            for day in days:
                with ui.column().classes("day-header p-2 items-center justify-center"):
                    ui.label(day.strftime("%a").capitalize()).classes("text-xs uppercase muted")
                    ui.label(day.strftime("%d")).classes("text-xl font-semibold")

            for tech_index, tech in enumerate(techs):
                name = tech["name"]
                with ui.column().classes("resource-cell p-3 justify-center gap-1"):
                    ui.label(name).classes("font-semibold")
                    details = " · ".join(
                        value for value in [tech.get("description"), tech.get("team")] if value
                    )
                    ui.label(details or "Ressource").classes("text-xs muted")

                for day in days:
                    state = features.availability_for_day(self.repo, name, day)
                    day_capacity = v13._availability_hours(self.repo, name, day)
                    day_allocations = [
                        row
                        for row in allocations
                        if str(row.get("Technicien") or "").strip() == name
                        and row.get("Date") == day
                    ]
                    planned = sum(v13._number(row.get("Heures")) for row in day_allocations)
                    classes = "day-cell gap-1"
                    if not state.get("available"):
                        classes += " unavailable-cell"
                    elif day.weekday() >= 5:
                        classes += " weekend-cell"

                    with ui.column().classes(classes):
                        if state.get("available") and state.get("hours"):
                            ui.label(state["hours"]).classes("text-[10px] availability-hours")
                        elif not state.get("available"):
                            ui.label(str(state.get("reason") or "Indisponible")).classes(
                                "text-[10px] unavailable-label"
                            )

                        if day_capacity > 0:
                            css = "text-[10px] muted"
                            if planned > day_capacity + 0.01:
                                css = "text-[10px] text-red-700 font-semibold"
                            ui.label(f"{planned:.1f}/{day_capacity:.1f} h").classes(css)

                        for allocation_index, allocation in enumerate(day_allocations):
                            segment = segments.get(str(allocation.get("IDSegment") or ""), {})
                            card_css = ui_module.PASTEL_CLASSES[
                                (tech_index + allocation_index) % len(ui_module.PASTEL_CLASSES)
                            ]
                            with ui.element("div").classes(f"shift-card {card_css}").on(
                                "click",
                                lambda _, s=segment: _open_segment_dialog_v14(self, segment=s)
                                if s
                                else None,
                            ):
                                ui.label(
                                    f"{allocation.get('NumeroProjet') or '—'} · {allocation.get('NomProjet') or ''}"
                                ).classes("text-xs font-semibold")
                                ui.label(
                                    str(segment.get("Description") or allocation.get("IDSegment") or "Allocation")
                                ).classes("text-xs")
                                ui.label(
                                    f"{v13._number(allocation.get('Heures')):.1f} h · {allocation.get('TypeAllocation')}"
                                ).classes("text-[11px] muted")


def _recalculate_from_ui(self: ui_module.PlannerUI) -> None:
    try:
        summary = rebuild_allocations(self.repo)
        self._after_write(
            f"Allocations recalculées : {summary['allocated_hours']:g} h allouées"
            + (
                f", {summary['unallocated_hours']:g} h sans capacité"
                if summary["unallocated_hours"] > 0
                else ""
            )
        )
    except Exception as exc:
        ui.notify(str(exc), type="negative")


def _open_effort_macro_dialog_v14(
    self: ui_module.PlannerUI,
    effort: dict[str, Any],
) -> None:
    self.interaction_lock = True
    row = int(effort.get("_row") or 0)
    linked = v13._linked_demands(self.repo, row)
    total = v13._number(effort.get("Efforts Prévus"))
    detailed = v13._segment_hours_for_effort(self.repo, row)

    with ui.dialog() as dialog, ui.card().classes("w-[760px] max-w-full"):
        ui.label(f"{effort.get('N° projet') or '—'} · {effort.get('Projet') or ''}").classes(
            "text-xl font-bold"
        )
        ui.label(
            f"{self._date_text(effort.get('Date de début'))} → "
            f"{self._date_text(effort.get('Date de fin')) or self._date_text(effort.get('Date de début'))}"
        ).classes("muted")
        ui.label(
            f"Effort macro : {total:g} h · Segments liés : {detailed:g} h · "
            f"Reste : {max(total - detailed, 0):g} h"
        ).classes("text-sm")
        ui.label(
            f"Ressource pressentie : {effort.get('Équipe/Technicien attitré') or '—'}"
        ).classes("text-sm")

        ui.separator()
        ui.label("Demandes liées").classes("font-semibold")
        if not linked:
            ui.label("Aucune demande MO liée.").classes("text-sm muted")
        for demand in linked:
            with ui.row().classes("w-full items-center border-b border-gray-100 py-2"):
                with ui.column().classes("gap-0"):
                    ui.label(str(demand.get("NoDemande") or "")).classes("font-semibold")
                    ui.label(
                        f"{demand.get('Statut') or ''} · {demand.get('CompetencesRequises') or 'Compétence non précisée'}"
                    ).classes("text-xs muted")
                ui.space()
                ui.button(
                    "Modifier",
                    icon="edit",
                    on_click=lambda d=demand: _edit_demand_from_medium_term(self, dialog, d),
                ).props("flat dense no-caps")
                ui.button(
                    "Segments",
                    icon="view_timeline",
                    on_click=lambda d=demand: _segments_from_medium_term(self, dialog, d),
                ).props("flat dense no-caps")

        ui.separator()
        with ui.row().classes("w-full justify-end"):
            ui.button("Fermer", on_click=dialog.close).props("flat no-caps")
            ui.button(
                "Nouvelle demande brouillon",
                icon="note_add",
                on_click=lambda: v13._create_demand_from_effort(self, effort, False, dialog),
            ).props("outline no-caps")
            ui.button(
                "Créer et soumettre",
                icon="send",
                on_click=lambda: v13._create_demand_from_effort(self, effort, True, dialog),
            ).props("unelevated no-caps color=primary")

    dialog.on("hide", lambda _: self._unlock())
    dialog.open()


def _edit_demand_from_medium_term(
    self: ui_module.PlannerUI,
    dialog: Any,
    demand: dict[str, Any],
) -> None:
    dialog.close()
    ui.timer(0.05, lambda: self.open_edit_request_dialog(demand), once=True)


def _segments_from_medium_term(
    self: ui_module.PlannerUI,
    dialog: Any,
    demand: dict[str, Any],
) -> None:
    dialog.close()
    ui.timer(0.05, lambda: v13._go_to_segments(self, demand), once=True)


def _render_dashboard_v14(self: ui_module.PlannerUI) -> None:
    demands = self.repo.demands()
    techs = schedulable_technicians(self.repo)
    pending = [row for row in demands if row.get("Statut") == "Soumise"]
    unassigned = _unassigned_segments(self.repo)
    allocations = allocation_records(self.repo)
    current_days = week_days(week_start())
    current_allocations = [
        row
        for row in allocations
        if row.get("Date") and current_days[0] <= row["Date"] <= current_days[-1]
    ]

    with ui.row().classes("w-full items-center"):
        with ui.column().classes("gap-0"):
            ui.label("Tableau de bord").classes("text-2xl font-bold")
            ui.label("Semaine du " + week_start().strftime("%d/%m/%Y")).classes("muted")
        ui.space()
        ui.button("Nouvelle demande", icon="add", on_click=self.open_new_request_dialog).props(
            "unelevated no-caps color=primary"
        )

    with ui.grid(columns=4).classes("w-full gap-4"):
        self.kpi("À approuver", len(pending), "approval", "Demandes au statut Soumise")
        self.kpi("À assigner", len(unassigned), "person_search", "Segments sans technicien")
        self.kpi(
            "Allocations cette semaine",
            len(current_allocations),
            "calendar_view_week",
            "Quarts générés par le moteur",
        )
        self.kpi("Ressources", len(techs), "groups", "Techniciens avec horaire actif")

    with ui.grid(columns=2).classes("w-full gap-4"):
        with ui.card().classes("section-card w-full"):
            with ui.row().classes("w-full items-center"):
                ui.label("Charge réelle — semaine courante").classes("text-lg font-semibold")
                ui.space()
                ui.button(
                    "Recalculer",
                    icon="calculate",
                    on_click=lambda: _recalculate_from_ui(self),
                ).props("flat dense no-caps")
            ui.label("Capacité selon les horaires; charge selon AllocationsMO.").classes(
                "text-xs muted"
            )
            loads = weekly_allocation_load(self.repo, week_start())[:12]
            if not loads:
                ui.label("Aucune ressource planifiable.").classes("muted")
            for load in loads:
                with ui.column().classes("w-full gap-1 mt-2"):
                    with ui.row().classes("w-full items-center"):
                        ui.label(load["name"]).classes("font-medium")
                        ui.space()
                        text = f'{load["planned"]:.1f} h / {load["weekly_capacity"]:.1f} h'
                        if load["pct"] is not None:
                            text += f" · {int(load['pct'])} %"
                        ui.label(text).classes("text-sm muted")
                    fraction = min(max((load["pct"] or 0) / 100, 0), 1)
                    ui.linear_progress(value=fraction).classes("w-full")
                    if (load["pct"] or 0) > 100:
                        ui.label(
                            f"Surcharge : {load['planned'] - load['weekly_capacity']:.1f} h"
                        ).classes("text-xs text-red-700")

        with ui.card().classes("section-card w-full"):
            ui.label("Travaux à planifier").classes("text-lg font-semibold")
            if not unassigned:
                ui.label("Aucun segment en attente d'assignation.").classes("muted")
            demands_lookup = demand_lookup(self.repo)
            for segment in unassigned[:10]:
                competence = segment_competence(segment, demands_lookup)
                with ui.row().classes("w-full items-center border-b border-gray-100 py-2"):
                    with ui.column().classes("gap-0"):
                        ui.label(
                            f"{segment.get('NumeroProjet') or '—'} · {segment.get('NomProjet') or ''}"
                        ).classes("font-medium")
                        ui.label(
                            f"{competence or 'Compétence non précisée'} · {v13._number(segment.get('HeuresPrevues')):g} h"
                        ).classes("text-xs muted")
                    ui.space()
                    ui.button(
                        "Planifier",
                        on_click=lambda s=segment: _open_segment_dialog_v14(self, segment=s),
                    ).props("flat dense no-caps")


def install_v14_features() -> None:
    if getattr(ui_module.PlannerUI, "_v14_features_installed", False):
        return

    for header in SEGMENT_EXTRA_HEADERS:
        if header not in v13.SEGMENT_HEADERS:
            v13.SEGMENT_HEADERS.append(header)
    if "À assigner" not in v13.SEGMENT_STATUSES:
        v13.SEGMENT_STATUSES.insert(0, "À assigner")
    MASTER_SHEETS.add(ALLOCATION_SHEET)

    # Les segments créés automatiquement à l'approbation héritent de la compétence,
    # de la priorité et sont flexibles par défaut.
    original_add_segment = v13.add_segment

    def add_segment_v14(repo: ExcelRepository, values: dict[str, Any]) -> str:
        data = dict(values)
        demand = demand_lookup(repo).get(str(data.get("NoDemande") or ""), {})
        if not data.get("CompetenceRequise"):
            data["CompetenceRequise"] = demand.get("CompetencesRequises")
        if not data.get("TypePlanification"):
            data["TypePlanification"] = "Flexible"
        if not data.get("Priorite"):
            data["Priorite"] = demand.get("Priorite") or "Normale"
        if not str(data.get("Technicien") or "").strip() and str(data.get("Statut") or "") not in {
            "Annulé",
            "Terminé",
        }:
            data["Statut"] = "À assigner"
        return original_add_segment(repo, data)

    v13.add_segment = add_segment_v14

    original_approve = ExcelRepository.approve_demand

    def approve_demand_v14(self: ExcelRepository, number: str, comment: str = "") -> None:
        original_approve(self, number, comment)
        rebuild_allocations(self)

    ExcelRepository.approve_demand = approve_demand_v14

    original_ensure = ExcelRepository.ensure_app_sheets

    def ensure_app_sheets_v14(self: ExcelRepository) -> None:
        original_ensure(self)
        ensure_v14_sheets(self)
        rebuild_allocations(self)

    ExcelRepository.ensure_app_sheets = ensure_app_sheets_v14

    # Les disponibilités modifiées depuis l'interface invalident les allocations.
    original_add_availability = features.add_availability
    original_delete_availability = features.delete_availability
    original_initialize_schedules = features.initialize_standard_schedules

    def add_availability_v14(repo: ExcelRepository, values: dict[str, Any]) -> str:
        ident = original_add_availability(repo, values)
        rebuild_allocations(repo)
        return ident

    def delete_availability_v14(repo: ExcelRepository, row_number: int) -> None:
        original_delete_availability(repo, row_number)
        rebuild_allocations(repo)

    def initialize_standard_schedules_v14(repo: ExcelRepository) -> int:
        created = original_initialize_schedules(repo)
        rebuild_allocations(repo)
        return created

    features.add_availability = add_availability_v14
    features.delete_availability = delete_availability_v14
    features.initialize_standard_schedules = initialize_standard_schedules_v14

    original_page_sheets = ui_module.PlannerUI._page_sheets

    def page_sheets_v14(self: ui_module.PlannerUI) -> list[str]:
        sheets = list(original_page_sheets(self))
        if self.current_page in {"planning", "segments", "dashboard"} and ALLOCATION_SHEET not in sheets:
            sheets.append(ALLOCATION_SHEET)
        return sheets

    ui_module.PlannerUI._page_sheets = page_sheets_v14
    ui_module.PlannerUI.render_planning = _render_operational_planning_v14
    ui_module.PlannerUI.render_segments = _render_segments_v14
    ui_module.PlannerUI.render_dashboard = _render_dashboard_v14

    # Le Gantt V1.3 résout ces fonctions au moment du clic.
    v13._open_segment_dialog = _open_segment_dialog_v14
    v13._open_effort_macro_dialog = _open_effort_macro_dialog_v14
    v13.weekly_segment_load = weekly_allocation_load

    ui_module.PlannerUI._v14_features_installed = True
