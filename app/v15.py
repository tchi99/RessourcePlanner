from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from nicegui import ui

from . import features
from . import ui as ui_module
from . import v13, v13_fixes, v14, v14_engine, v14_fixes
from .bugfixes import schedulable_technicians
from .excel_repository import ExcelRepository, _date_from_any
from .services import week_days, week_start
from .v15_engine import (
    allocation_records,
    create_manual_allocation,
    delete_manual_allocation,
    ensure_v15_sheets,
    rebuild_allocations,
    release_manual_allocation,
    update_manual_allocation,
    weekly_allocation_load,
    _truthy,
)


BUSINESS_DEMAND_FIELDS = {
    "NumeroProjet",
    "NomProjet",
    "Client",
    "ChargeProjet",
    "TypeDemande",
    "Priorite",
    "DateDebutSouhaitee",
    "DateFinSouhaitee",
    "Description",
    "SiteClient",
    "Lieu",
    "NombreRessources",
    "CompetencesRequises",
    "TempsEstimeHeures",
    "TempsEstimeJours",
    "TechnicienPropose",
}


def _overlaps_week(start_value: Any, end_value: Any, week: date) -> bool:
    start = _date_from_any(start_value)
    end = _date_from_any(end_value) or start
    return bool(start and end and start <= week + timedelta(days=6) and end >= week)


def _unassigned_segments_for_week(repo: ExcelRepository, week: date) -> list[dict[str, Any]]:
    return [
        row
        for row in v13.segment_records(repo, include_cancelled=False)
        if not str(row.get("Technicien") or "").strip()
        and str(row.get("Statut") or "") not in {"Annulé", "Terminé"}
        and _overlaps_week(row.get("DateDebut"), row.get("DateFin"), week)
    ]


def _pending_demands_for_week(repo: ExcelRepository, week: date) -> list[dict[str, Any]]:
    return [
        row
        for row in repo.demands()
        if str(row.get("Statut") or "") == "Soumise"
        and _overlaps_week(
            row.get("DateDebutSouhaitee"), row.get("DateFinSouhaitee"), week
        )
    ]


def _pending_covers_day(demand: dict[str, Any], day: date) -> bool:
    start = _date_from_any(demand.get("DateDebutSouhaitee"))
    end = _date_from_any(demand.get("DateFinSouhaitee")) or start
    return bool(start and end and start <= day <= end)


def _allocation_style(
    allocation: dict[str, Any], overloaded: bool
) -> tuple[str, str]:
    if _truthy(allocation.get("HorsHoraire")):
        return "background:#ffedd5;border-left:4px solid #ea580c;", "Hors horaire"
    if overloaded:
        return "background:#fee2e2;border-left:4px solid #dc2626;", "Surchargé"
    if _truthy(allocation.get("Verrouillee")) or str(
        allocation.get("TypeAllocation") or ""
    ) == "Fixe":
        return "background:#ede9fe;border-left:4px solid #7c3aed;", "Fixe / verrouillé"
    return "background:#dbeafe;border-left:4px solid #2563eb;", "Flexible"


def _move_dashboard_week(self: ui_module.PlannerUI, delta: int) -> None:
    self.dashboard_week = getattr(self, "dashboard_week", week_start()) + timedelta(
        weeks=delta
    )
    self.render_content.refresh()


def _reset_dashboard_week(self: ui_module.PlannerUI) -> None:
    self.dashboard_week = week_start()
    self.render_content.refresh()


def _open_manual_allocation_dialog(
    self: ui_module.PlannerUI,
    allocation: dict[str, Any] | None = None,
    segment: dict[str, Any] | None = None,
    default_date: date | None = None,
) -> None:
    self.interaction_lock = True
    editing = allocation is not None
    segments = [
        row
        for row in v13.segment_records(self.repo, include_cancelled=False)
        if str(row.get("Statut") or "") not in {"Annulé", "Terminé"}
    ]
    segment_lookup = {str(row.get("IDSegment") or ""): row for row in segments}
    segment_options = {
        str(row.get("IDSegment") or ""): (
            f"{row.get('IDSegment')} — {row.get('NumeroProjet') or '—'} · "
            f"{row.get('NomProjet') or ''} · {v13._number(row.get('HeuresPrevues')):g} h"
        )
        for row in segments
        if row.get("IDSegment")
    }

    initial_segment_id = ""
    if allocation:
        initial_segment_id = str(allocation.get("IDSegment") or "")
    elif segment:
        initial_segment_id = str(segment.get("IDSegment") or "")
    initial_segment = segment_lookup.get(initial_segment_id, segment or {})

    tech_options = [row["name"] for row in schedulable_technicians(self.repo)]
    initial_tech = str(
        (allocation or {}).get("Technicien")
        or initial_segment.get("Technicien")
        or ""
    ).strip()
    if initial_tech and initial_tech not in tech_options:
        tech_options.append(initial_tech)

    initial_day = (
        _date_from_any((allocation or {}).get("Date"))
        or default_date
        or _date_from_any(initial_segment.get("DateDebut"))
        or self.current_week
    )

    with ui.dialog() as dialog, ui.card().classes("w-[720px] max-w-full"):
        ui.label(
            "Modifier / verrouiller le quart" if editing else "Nouveau quart manuel"
        ).classes("text-xl font-bold")
        ui.label(
            "Un quart manuel est verrouillé : les recalculs automatiques redistribuent le reste autour de cette décision."
        ).classes("text-xs muted")

        segment_select = ui.select(
            segment_options,
            label="Segment",
            value=initial_segment_id or None,
            with_input=True,
            clearable=False,
        ).classes("w-full")
        if editing:
            segment_select.props("readonly")

        with ui.row().classes("w-full"):
            technician = ui.select(
                tech_options,
                label="Technicien",
                value=initial_tech or None,
                with_input=True,
                clearable=False,
            ).classes("flex-1")
            day = ui.input(
                "Date",
                value=initial_day.isoformat() if initial_day else "",
            ).props("type=date").classes("flex-1")
            hours = ui.number(
                "Heures",
                value=v13._number((allocation or {}).get("Heures")) or None,
                min=0.25,
                step=0.25,
            ).classes("flex-1")

        hors_horaire = ui.checkbox(
            "Autoriser explicitement ce quart hors horaire standard",
            value=_truthy((allocation or {}).get("HorsHoraire")),
        )
        note = ui.input(
            "Note",
            value=str((allocation or {}).get("Note") or ""),
        ).classes("w-full")

        def save() -> None:
            if not segment_select.value or not technician.value or not day.value:
                ui.notify("Segment, technicien et date sont requis.", type="warning")
                return
            try:
                if editing:
                    update_manual_allocation(
                        self.repo,
                        str(allocation.get("IDAllocation") or ""),
                        str(technician.value),
                        day.value,
                        hours.value,
                        bool(hors_horaire.value),
                        str(note.value or ""),
                    )
                    message = "Quart verrouillé et mis à jour"
                else:
                    create_manual_allocation(
                        self.repo,
                        str(segment_select.value),
                        str(technician.value),
                        day.value,
                        hours.value,
                        bool(hors_horaire.value),
                        str(note.value or ""),
                    )
                    message = "Quart manuel créé"
                dialog.close()
                self._after_write(message)
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        def release() -> None:
            try:
                release_manual_allocation(
                    self.repo, str(allocation.get("IDAllocation") or "")
                )
                dialog.close()
                self._after_write("Quart remis en planification automatique")
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        def delete() -> None:
            try:
                delete_manual_allocation(
                    self.repo, str(allocation.get("IDAllocation") or "")
                )
                dialog.close()
                self._after_write("Quart manuel supprimé; le reliquat a été recalculé")
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        with ui.row().classes("w-full justify-end"):
            ui.button("Annuler", on_click=dialog.close).props("flat no-caps")
            if editing and _truthy(allocation.get("Verrouillee")):
                ui.button(
                    "Revenir à l'automatique",
                    icon="autorenew",
                    on_click=release,
                ).props("outline no-caps")
                ui.button(
                    "Supprimer le quart",
                    icon="delete",
                    on_click=delete,
                ).props("flat no-caps color=negative")
            ui.button("Enregistrer et verrouiller", icon="lock", on_click=save).props(
                "unelevated no-caps color=primary"
            )

    dialog.on("hide", lambda _: self._unlock())
    dialog.open()


def _render_operational_planning_v15(self: ui_module.PlannerUI) -> None:
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
    demands = v14_engine.demand_lookup(self.repo)
    unassigned = _unassigned_segments_for_week(self.repo, self.current_week)
    pending = _pending_demands_for_week(self.repo, self.current_week)

    with ui.row().classes("w-full items-center"):
        with ui.column().classes("gap-0"):
            ui.label("Planning opérationnel").classes("text-2xl font-bold")
            ui.label(
                "Bleu = flexible · violet = fixe/verrouillé · rouge = surcharge · orange = hors horaire · gris = en attente d'approbation."
            ).classes("muted")
        ui.space()
        ui.button(
            "Quart manuel",
            icon="add_task",
            on_click=lambda: _open_manual_allocation_dialog(self),
        ).props("outline no-caps")
        ui.button(
            "Recalculer",
            icon="calculate",
            on_click=lambda: _recalculate_from_ui_v15(self),
        ).props("outline no-caps")
        ui.button(icon="chevron_left", on_click=self.previous_week).props("flat round")
        ui.button("Aujourd'hui", on_click=self.today_week).props("outline no-caps")
        ui.button(icon="chevron_right", on_click=self.next_week).props("flat round")
        ui.label(f"{days[0].strftime('%d %b')} – {days[-1].strftime('%d %b %Y')}").classes(
            "font-semibold ml-2"
        )

    if unassigned:
        with ui.card().classes("section-card w-full"):
            ui.label(f"Travaux à planifier cette semaine ({len(unassigned)})").classes(
                "text-lg font-semibold"
            )
            with ui.row().classes("w-full gap-2 flex-wrap"):
                for segment in unassigned[:16]:
                    competence = v14_engine.segment_competence(segment, demands) or "Compétence non précisée"
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
                            on_click=lambda s=segment: v14._open_segment_dialog_v14(self, segment=s),
                        ).props("flat dense no-caps")

    if pending:
        with ui.card().classes("section-card w-full"):
            ui.label(f"En attente d'approbation dans cette semaine ({len(pending)})").classes(
                "text-lg font-semibold"
            )
            ui.label(
                "Ces besoins sont visibles pour anticipation, mais ils ne consomment aucune capacité tant qu'ils ne sont pas approuvés."
            ).classes("text-xs muted")
            with ui.row().classes("w-full gap-2 flex-wrap"):
                for demand in pending[:16]:
                    with ui.card().classes("p-3 min-w-[250px] max-w-[340px]").style(
                        "background:#f9fafb;border:1px dashed #9ca3af;"
                    ):
                        ui.label(
                            f"{demand.get('NumeroProjet') or '—'} · {demand.get('NomProjet') or ''}"
                        ).classes("text-sm font-semibold")
                        ui.label(
                            f"{demand.get('CompetencesRequises') or 'Compétence non précisée'} · "
                            f"{int(v13._number(demand.get('NombreRessources')) or 1)} ressource(s)"
                        ).classes("text-xs")
                        ui.label(
                            f"{self._date_text(demand.get('DateDebutSouhaitee'))} → {self._date_text(demand.get('DateFinSouhaitee'))}"
                        ).classes("text-xs muted")

    with ui.scroll_area().classes("w-full h-[calc(100vh-310px)]"):
        with ui.grid(columns=8).classes("schedule-grid gap-0"):
            with ui.column().classes("day-header p-3 justify-center"):
                ui.label("Ressource").classes("font-semibold")
            for day in days:
                with ui.column().classes("day-header p-2 items-center justify-center"):
                    ui.label(day.strftime("%a").capitalize()).classes("text-xs uppercase muted")
                    ui.label(day.strftime("%d")).classes("text-xl font-semibold")

            for tech in techs:
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
                    pending_day = [
                        row
                        for row in pending
                        if str(row.get("TechnicienPropose") or "").strip() == name
                        and _pending_covers_day(row, day)
                        and v13._availability_hours(self.repo, name, day) > 0
                    ]
                    planned = sum(v13._number(row.get("Heures")) for row in day_allocations)
                    overloaded = planned > day_capacity + 0.01 and day_capacity >= 0
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

                        if planned > 0 or day_capacity > 0:
                            css = "text-[10px] muted"
                            if overloaded:
                                css = "text-[10px] text-red-700 font-semibold"
                            ui.label(f"{planned:.1f}/{day_capacity:.1f} h").classes(css)

                        for allocation in day_allocations:
                            segment = segments.get(str(allocation.get("IDSegment") or ""), {})
                            style, label = _allocation_style(allocation, overloaded)
                            with ui.element("div").classes("shift-card").style(style).on(
                                "click",
                                lambda _, a=allocation: _open_manual_allocation_dialog(
                                    self, allocation=a
                                ),
                            ):
                                ui.label(
                                    f"{allocation.get('NumeroProjet') or '—'} · {allocation.get('NomProjet') or ''}"
                                ).classes("text-xs font-semibold")
                                ui.label(
                                    str(segment.get("Description") or allocation.get("IDSegment") or "Allocation")
                                ).classes("text-xs")
                                lock = " · 🔒" if _truthy(allocation.get("Verrouillee")) else ""
                                ui.label(
                                    f"{v13._number(allocation.get('Heures')):.1f} h · {label}{lock}"
                                ).classes("text-[11px] muted")

                        for demand in pending_day:
                            with ui.element("div").classes("shift-card").style(
                                "background:#f3f4f6;border:2px dashed #9ca3af;opacity:.9;"
                            ):
                                ui.label(
                                    f"{demand.get('NumeroProjet') or '—'} · {demand.get('NomProjet') or ''}"
                                ).classes("text-xs font-semibold")
                                ui.label(str(demand.get("Description") or "")).classes("text-xs")
                                ui.label("En attente d'approbation · 0 h de charge").classes(
                                    "text-[11px] text-gray-600"
                                )


def _recalculate_from_ui_v15(self: ui_module.PlannerUI) -> None:
    try:
        summary = rebuild_allocations(self.repo)
        self._after_write(
            f"Allocations recalculées : {summary['allocated_hours']:g} h allouées · "
            f"{summary['locked_allocations']} quart(s) verrouillé(s)"
            + (
                f" · {summary['unallocated_hours']:g} h sans capacité"
                if summary["unallocated_hours"] > 0
                else ""
            )
        )
    except Exception as exc:
        ui.notify(str(exc), type="negative")


def _render_dashboard_v15(self: ui_module.PlannerUI) -> None:
    if not hasattr(self, "dashboard_week"):
        self.dashboard_week = week_start()
    selected_week: date = self.dashboard_week
    days = week_days(selected_week)
    demands = self.repo.demands()
    techs = schedulable_technicians(self.repo)
    pending_all = [row for row in demands if str(row.get("Statut") or "") == "Soumise"]
    unassigned = _unassigned_segments_for_week(self.repo, selected_week)
    allocations = [
        row
        for row in allocation_records(self.repo)
        if row.get("Date") and days[0] <= row["Date"] <= days[-1]
    ]

    with ui.row().classes("w-full items-center"):
        with ui.column().classes("gap-0"):
            ui.label("Tableau de bord").classes("text-2xl font-bold")
            ui.label("Semaine du " + selected_week.strftime("%d/%m/%Y")).classes("muted")
        ui.space()
        ui.button(icon="chevron_left", on_click=lambda: _move_dashboard_week(self, -1)).props(
            "flat round"
        )
        ui.button("Aujourd'hui", on_click=lambda: _reset_dashboard_week(self)).props(
            "outline no-caps"
        )
        ui.button(icon="chevron_right", on_click=lambda: _move_dashboard_week(self, 1)).props(
            "flat round"
        )
        ui.button("Nouvelle demande", icon="add", on_click=self.open_new_request_dialog).props(
            "unelevated no-caps color=primary"
        )

    with ui.grid(columns=4).classes("w-full gap-4"):
        self.kpi("À approuver", len(pending_all), "approval", "Demandes soumises ou à réapprouver")
        self.kpi("À assigner", len(unassigned), "person_search", "Segments de la semaine sans technicien")
        self.kpi("Allocations", len(allocations), "calendar_view_week", "Quarts de la semaine sélectionnée")
        self.kpi("Ressources", len(techs), "groups", "Techniciens avec horaire actif")

    with ui.grid(columns=2).classes("w-full gap-4"):
        with ui.card().classes("section-card w-full"):
            with ui.row().classes("w-full items-center"):
                ui.label("Charge réelle — semaine sélectionnée").classes("text-lg font-semibold")
                ui.space()
                ui.button(
                    "Recalculer",
                    icon="calculate",
                    on_click=lambda: _recalculate_from_ui_v15(self),
                ).props("flat dense no-caps")
            ui.label(
                "La capacité provient de l'horaire standard. Les quarts hors horaire restent visibles séparément."
            ).classes("text-xs muted")
            loads = weekly_allocation_load(self.repo, selected_week)[:14]
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
                        if load["overtime"] > 0:
                            text += f" · {load['overtime']:.1f} h hors horaire"
                        ui.label(text).classes("text-sm muted")
                    fraction = min(max((load["pct"] or 0) / 100, 0), 1)
                    ui.linear_progress(value=fraction).classes("w-full")
                    if (load["pct"] or 0) > 100:
                        ui.label(
                            f"Surcharge : {load['planned'] - load['weekly_capacity']:.1f} h"
                        ).classes("text-xs text-red-700")

        with ui.card().classes("section-card w-full"):
            ui.label("Travaux à planifier — semaine sélectionnée").classes(
                "text-lg font-semibold"
            )
            if not unassigned:
                ui.label("Aucun segment en attente d'assignation dans cette semaine.").classes(
                    "muted"
                )
            demands_lookup = v14_engine.demand_lookup(self.repo)
            for segment in unassigned[:12]:
                competence = v14_engine.segment_competence(segment, demands_lookup)
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
                        on_click=lambda s=segment: v14._open_segment_dialog_v14(self, segment=s),
                    ).props("flat dense no-caps")


def _render_medium_term_v15(self: ui_module.PlannerUI) -> None:
    if not hasattr(self, "medium_term_start"):
        self.medium_term_start = week_start() - timedelta(weeks=2)

    window_start: date = self.medium_term_start
    weeks = [window_start + timedelta(weeks=index) for index in range(v13.GANTT_WEEKS)]
    window_end = weeks[-1] + timedelta(days=6)
    current = week_start()
    efforts = [
        effort
        for effort in self.repo.efforts(include_closed=False)
        if v13._gantt_overlap(effort, window_start, window_end)
    ]

    with ui.row().classes("w-full items-center"):
        with ui.column().classes("gap-0"):
            ui.label("Planification moyen terme").classes("text-2xl font-bold")
            ui.label(
                "Vue macro de Liste_Effort. La semaine courante est encadrée en bleu."
            ).classes("muted")
        ui.space()
        ui.button(icon="chevron_left", on_click=lambda: v13._move_medium_term(self, -8)).props("flat round")
        ui.button("Aujourd'hui", on_click=lambda: v13._reset_medium_term(self)).props("outline no-caps")
        ui.button(icon="chevron_right", on_click=lambda: v13._move_medium_term(self, 8)).props("flat round")
        ui.label(f"{window_start.strftime('%d/%m/%Y')} → {window_end.strftime('%d/%m/%Y')}").classes(
            "font-semibold ml-2"
        )

    if not efforts:
        with ui.card().classes("section-card w-full"):
            ui.label("Aucun effort moyen terme dans cette fenêtre.").classes("muted")
        return

    with ui.scroll_area().classes("w-full h-[calc(100vh-190px)]"):
        with ui.element("div").classes("gantt-grid-v13").style(
            f"display:grid; grid-template-columns:300px repeat({v13.GANTT_WEEKS}, minmax(100px, 1fr)); "
            f"min-width:{300 + 100 * v13.GANTT_WEEKS}px; width:100%;"
        ):
            with ui.column().classes("gantt-header p-2 justify-center"):
                ui.label("Projet / ressource").classes("font-semibold")
            for week in weeks:
                header = ui.column().classes("gantt-header p-1 items-center justify-center")
                if week == current:
                    header.style(
                        "background:#dbeafe !important;border-left:3px solid #2563eb;border-right:3px solid #2563eb;"
                    )
                with header:
                    ui.label(week.strftime("%d %b")).classes("text-[10px] font-semibold")
                    if week == current:
                        ui.label("Cette semaine").classes("text-[9px] text-blue-700")

            for effort_index, effort in enumerate(efforts):
                effort_row = int(effort.get("_row") or 0)
                total = v13._number(effort.get("Efforts Prévus"))
                detailed = v13._segment_hours_for_effort(self.repo, effort_row)
                remaining = max(total - detailed, 0.0)
                linked = v13._linked_demands(self.repo, effort_row)

                with ui.column().classes("gantt-label p-2 gap-0").on(
                    "click", lambda _, e=effort: v13._open_effort_macro_dialog(self, e)
                ):
                    ui.label(f"{effort.get('N° projet') or '—'} · {effort.get('Projet') or ''}").classes(
                        "text-xs font-semibold"
                    )
                    ui.label(str(effort.get("Équipe/Technicien attitré") or "Non assigné")).classes(
                        "text-[10px] muted"
                    )
                    ui.label(f"{total:g} h · détaillé {detailed:g} h · reste {remaining:g} h").classes(
                        "text-[10px] muted"
                    )
                    if linked:
                        ui.label(
                            ", ".join(str(d.get("NoDemande") or "") for d in linked)
                        ).classes("text-[10px] text-blue-700")

                color = v13_fixes.GANTT_COLORS[effort_index % len(v13_fixes.GANTT_COLORS)]
                for week in weeks:
                    active = v13._gantt_overlap(effort, week, week + timedelta(days=6))
                    cell = ui.element("div").classes(
                        "gantt-cell gantt-active" if active else "gantt-cell"
                    )
                    styles: list[str] = []
                    if active:
                        styles.append(
                            f"background-color:{color} !important;border-color:#cbd5e1;"
                        )
                    if week == current:
                        styles.append(
                            "border-left:3px solid #2563eb !important;border-right:3px solid #2563eb !important;"
                        )
                    if styles:
                        cell.style("".join(styles))


def _estimated_hours_per_resource(repo: ExcelRepository, demand: dict[str, Any], count: int) -> float:
    total_hours = v13._number(demand.get("TempsEstimeHeures"))
    if total_hours > 0:
        return round(total_hours / max(count, 1), 2)
    proposed = str(demand.get("TechnicienPropose") or "").strip()
    return round(v13_fixes._estimated_segment_hours(repo, demand, proposed), 2)


def install_v15_features() -> None:
    if getattr(ui_module.PlannerUI, "_v15_features_installed", False):
        return

    # Le moteur V1.5 remplace le recalcul V1.4 partout où celui-ci est résolu au runtime.
    v14_engine.rebuild_allocations = rebuild_allocations
    v14_engine.allocation_records = allocation_records
    v14_engine.weekly_allocation_load = weekly_allocation_load
    v14.rebuild_allocations = rebuild_allocations
    v14.allocation_records = allocation_records
    v14.weekly_allocation_load = weekly_allocation_load
    v14_fixes.rebuild_allocations = rebuild_allocations
    v13.weekly_segment_load = weekly_allocation_load

    original_ensure = ExcelRepository.ensure_app_sheets

    def ensure_app_sheets_v15(self: ExcelRepository) -> None:
        original_ensure(self)
        ensure_v15_sheets(self)
        rebuild_allocations(self)

    ExcelRepository.ensure_app_sheets = ensure_app_sheets_v15

    ui_module.PlannerUI.render_planning = _render_operational_planning_v15
    v13._render_operational_planning = _render_operational_planning_v15
    ui_module.PlannerUI.render_dashboard = _render_dashboard_v15
    ui_module.PlannerUI.render_medium_term = _render_medium_term_v15
    v13._render_medium_term = _render_medium_term_v15

    ui_module.PlannerUI._v15_features_installed = True