from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from nicegui import ui

from . import features
from . import ui as ui_module
from .bugfixes import schedulable_technicians
from .excel_repository import (
    DEMAND_HEADERS,
    ExcelRepository,
    MASTER_SHEETS,
    _as_matrix,
    _date_from_any,
)
from .services import week_days, week_start
from .segment_repository import (
    SEGMENT_HEADERS,
    SEGMENT_SHEET,
    SEGMENT_TABLE,
    SEGMENT_STATUSES,
    add_segment,
    ensure_segment_sheet as _ensure_v13_sheets,
    number as _number,
    segment_records,
    update_segment,
)


SOURCE_EFFORT_FIELD = "SourceEffortRow"
GANTT_WEEKS = 16




def _norm_project(value: Any) -> str:
    if value in (None, ""):
        return ""
    text = str(value).strip()
    try:
        number = float(text.replace(",", "."))
        if number.is_integer():
            return str(int(number))
    except (TypeError, ValueError):
        pass
    return text.lower()














def _parse_time_hours(text: str) -> float:
    raw = str(text or "").strip()
    if not raw or ":" not in raw:
        return 0.0
    try:
        hour, minute = raw.split(":", 1)
        return int(hour) + int(minute[:2]) / 60.0
    except (TypeError, ValueError):
        return 0.0


def _availability_hours(repo: ExcelRepository, technician: str, day: date) -> float:
    state = features.availability_for_day(repo, technician, day)
    if not state.get("available"):
        return 0.0
    raw = str(state.get("hours") or "")
    if "–" in raw:
        start, end = raw.split("–", 1)
    elif "-" in raw:
        start, end = raw.split("-", 1)
    else:
        return 0.0
    start_h = _parse_time_hours(start)
    end_h = _parse_time_hours(end)
    if end_h < start_h:
        end_h += 24
    return max(end_h - start_h, 0.0)


def _segment_dates(segment: dict[str, Any]) -> tuple[date | None, date | None]:
    start = _date_from_any(segment.get("DateDebut"))
    end = _date_from_any(segment.get("DateFin")) or start
    return start, end


def _segment_covers_day(segment: dict[str, Any], day: date) -> bool:
    start, end = _segment_dates(segment)
    return bool(start and end and start <= day <= end)


def segment_hours_for_day(repo: ExcelRepository, segment: dict[str, Any], day: date) -> float:
    if str(segment.get("Statut") or "") == "Annulé" or not _segment_covers_day(segment, day):
        return 0.0
    technician = str(segment.get("Technicien") or "").strip()
    if not technician:
        return 0.0
    day_capacity = _availability_hours(repo, technician, day)
    if day_capacity <= 0:
        return 0.0
    start, end = _segment_dates(segment)
    if not start or not end:
        return 0.0
    total_capacity = 0.0
    cursor = start
    while cursor <= end:
        total_capacity += _availability_hours(repo, technician, cursor)
        cursor += timedelta(days=1)
    if total_capacity <= 0:
        return 0.0
    return _number(segment.get("HeuresPrevues")) * day_capacity / total_capacity


def weekly_segment_load(repo: ExcelRepository, start: date) -> list[dict[str, Any]]:
    techs = {t["name"]: t for t in schedulable_technicians(repo)}
    segments = segment_records(repo, include_cancelled=False)
    days = week_days(start)
    result: list[dict[str, Any]] = []
    for name, info in techs.items():
        capacity = sum(_availability_hours(repo, name, day) for day in days)
        planned = 0.0
        for segment in segments:
            if str(segment.get("Technicien") or "").strip() != name:
                continue
            planned += sum(segment_hours_for_day(repo, segment, day) for day in days)
        pct = round(planned / capacity * 100, 0) if capacity else None
        result.append(
            {
                "name": name,
                "planned": round(planned, 1),
                "weekly_capacity": round(capacity, 1),
                "pct": pct,
                "team": info.get("team") or "",
                "description": info.get("description") or "",
            }
        )
    result.sort(key=lambda row: (-(row["pct"] or -1), row["name"]))
    return result


def segments_for_week(repo: ExcelRepository, start: date) -> list[dict[str, Any]]:
    end = start + timedelta(days=6)
    result = []
    for segment in segment_records(repo, include_cancelled=False):
        seg_start, seg_end = _segment_dates(segment)
        if seg_start and seg_end and seg_start <= end and seg_end >= start:
            result.append(segment)
    return result


def _effort_options(repo: ExcelRepository, project_number: Any | None = None) -> dict[str, str]:
    target = _norm_project(project_number)
    options: dict[str, str] = {}
    for effort in repo.efforts(include_closed=False):
        if target and _norm_project(effort.get("N° projet")) != target:
            continue
        row = int(effort.get("_row") or 0)
        if not row:
            continue
        start = _date_from_any(effort.get("Date de début"))
        end = _date_from_any(effort.get("Date de fin"))
        details = str(effort.get("Précision") or effort.get("Compétence") or "")
        dates = ""
        if start:
            dates = start.strftime("%d/%m/%Y")
            if end:
                dates += f" → {end.strftime('%d/%m/%Y')}"
        options[str(row)] = (
            f"{effort.get('N° projet') or '—'} · {details or effort.get('Projet') or ''}"
            f" · {dates} · {_number(effort.get('Efforts Prévus')):g} h"
        )
    return options


def _source_effort_for_demand(demand: dict[str, Any]) -> str | None:
    value = demand.get(SOURCE_EFFORT_FIELD)
    if value in (None, ""):
        return None
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return str(value)


def _render_dashboard_v13(self: ui_module.PlannerUI) -> None:
    demands = self.repo.demands()
    segments = segments_for_week(self.repo, week_start())
    techs = schedulable_technicians(self.repo)
    pending = [d for d in demands if d.get("Statut") == "Soumise"]
    planning = [d for d in demands if d.get("Statut") == "En planification"]

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
        self.kpi("En planification", len(planning), "event_note", "Demandes à segmenter")
        self.kpi("Segments cette semaine", len(segments), "view_timeline", "Planification opérationnelle")
        self.kpi("Ressources", len(techs), "groups", "Techniciens avec horaire actif")

    with ui.grid(columns=2).classes("w-full gap-4"):
        with ui.card().classes("section-card w-full"):
            ui.label("Charge réelle — semaine courante").classes("text-lg font-semibold")
            ui.label(
                "Capacité calculée depuis les horaires standards, vacances et jours fériés. "
                "Charge calculée depuis SegmentsMO."
            ).classes("text-xs muted")
            loads = weekly_segment_load(self.repo, week_start())[:12]
            if not loads:
                ui.label("Aucune ressource planifiable détectée.").classes("muted")
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
                        overload = load["planned"] - load["weekly_capacity"]
                        ui.label(f"Surcharge estimée : {overload:.1f} h").classes("text-xs text-red-700")

        with ui.card().classes("section-card w-full"):
            with ui.row().classes("w-full items-center"):
                ui.label("Demandes à approuver").classes("text-lg font-semibold")
                ui.space()
                ui.button("Voir tout", on_click=lambda: self.navigate("requests")).props("flat no-caps")
            if not pending:
                ui.label("Aucune demande en attente.").classes("muted")
            for demand in pending[:8]:
                with ui.row().classes("w-full items-center border-b border-gray-100 py-2"):
                    with ui.column().classes("gap-0"):
                        ui.label(str(demand.get("NoDemande") or "")).classes("font-semibold")
                        ui.label(
                            f"{demand.get('NumeroProjet') or '—'} · {demand.get('NomProjet') or ''}"
                        ).classes("text-sm")
                    ui.space()
                    ui.label(str(demand.get("Priorite") or "Normale")).classes("text-xs muted")


def _render_operational_planning(self: ui_module.PlannerUI) -> None:
    days = week_days(self.current_week)
    techs = schedulable_technicians(self.repo)
    segments = segment_records(self.repo, include_cancelled=False)

    with ui.row().classes("w-full items-center"):
        with ui.column().classes("gap-0"):
            ui.label("Planning opérationnel").classes("text-2xl font-bold")
            ui.label("Vue Shifts alimentée uniquement par les segments de demandes.").classes("muted")
        ui.space()
        ui.button(icon="chevron_left", on_click=self.previous_week).props("flat round")
        ui.button("Aujourd'hui", on_click=self.today_week).props("outline no-caps")
        ui.button(icon="chevron_right", on_click=self.next_week).props("flat round")
        ui.label(f"{days[0].strftime('%d %b')} – {days[-1].strftime('%d %b %Y')}").classes(
            "font-semibold ml-2"
        )

    with ui.scroll_area().classes("w-full h-[calc(100vh-190px)]"):
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

                tech_segments = [
                    segment
                    for segment in segments
                    if str(segment.get("Technicien") or "").strip() == name
                ]
                for day in days:
                    state = features.availability_for_day(self.repo, name, day)
                    classes = "day-cell gap-1"
                    if not state.get("available"):
                        classes += " unavailable-cell"
                    elif day.weekday() >= 5:
                        classes += " weekend-cell"
                    with ui.column().classes(classes):
                        day_capacity = _availability_hours(self.repo, name, day)
                        covered = [
                            segment for segment in tech_segments if _segment_covers_day(segment, day)
                        ]
                        if state.get("available") and state.get("hours"):
                            ui.label(state["hours"]).classes("text-[10px] availability-hours")
                        elif not state.get("available"):
                            ui.label(str(state.get("reason") or "Indisponible")).classes(
                                "text-[10px] unavailable-label"
                            )
                            if covered:
                                ui.label("⚠ Segment couvre ce jour").classes(
                                    "text-[10px] text-red-700 font-semibold"
                                )

                        visible = [
                            (segment, segment_hours_for_day(self.repo, segment, day))
                            for segment in covered
                            if state.get("available")
                        ]
                        total_planned = sum(hours for _, hours in visible)
                        if day_capacity and total_planned > day_capacity + 0.01:
                            ui.label(f"⚠ {total_planned:.1f} h / {day_capacity:.1f} h").classes(
                                "text-[10px] text-red-700 font-semibold"
                            )

                        for segment_index, (segment, planned_hours) in enumerate(visible):
                            css = ui_module.PASTEL_CLASSES[
                                (tech_index + segment_index) % len(ui_module.PASTEL_CLASSES)
                            ]
                            with ui.element("div").classes(f"shift-card {css}").on(
                                "click", lambda _, s=segment: _open_segment_dialog(self, segment=s)
                            ):
                                ui.label(
                                    f"{segment.get('NumeroProjet') or '—'} · {segment.get('NomProjet') or ''}"
                                ).classes("text-xs font-semibold")
                                ui.label(
                                    str(segment.get("Description") or segment.get("IDSegment") or "Segment")
                                ).classes("text-xs")
                                if planned_hours:
                                    ui.label(f"{planned_hours:.1f} h").classes("text-[11px] muted")


def _gantt_overlap(effort: dict[str, Any], start: date, end: date) -> bool:
    e_start = _date_from_any(effort.get("Date de début"))
    e_end = _date_from_any(effort.get("Date de fin")) or e_start
    return bool(e_start and e_end and e_start <= end and e_end >= start)


def _linked_demands(repo: ExcelRepository, effort_row: int) -> list[dict[str, Any]]:
    linked = []
    for demand in repo.demands():
        value = demand.get(SOURCE_EFFORT_FIELD)
        try:
            if int(float(value)) == int(effort_row):
                linked.append(demand)
        except (TypeError, ValueError):
            continue
    return linked


def _segment_hours_for_effort(repo: ExcelRepository, effort_row: int) -> float:
    total = 0.0
    for segment in segment_records(repo, include_cancelled=False):
        try:
            if int(float(segment.get("SourceEffortRow"))) == int(effort_row):
                total += _number(segment.get("HeuresPrevues"))
        except (TypeError, ValueError):
            continue
    return total


def _render_medium_term(self: ui_module.PlannerUI) -> None:
    if not hasattr(self, "medium_term_start"):
        self.medium_term_start = week_start() - timedelta(weeks=2)
    window_start: date = self.medium_term_start
    weeks = [window_start + timedelta(weeks=index) for index in range(GANTT_WEEKS)]
    window_end = weeks[-1] + timedelta(days=6)
    efforts = [
        effort
        for effort in self.repo.efforts(include_closed=False)
        if _gantt_overlap(effort, window_start, window_end)
    ]

    with ui.row().classes("w-full items-center"):
        with ui.column().classes("gap-0"):
            ui.label("Planification moyen terme").classes("text-2xl font-bold")
            ui.label(
                "Vue macro de Liste_Effort. Une barre représente une fenêtre de besoin, pas un quart de travail."
            ).classes("muted")
        ui.space()
        ui.button(icon="chevron_left", on_click=lambda: _move_medium_term(self, -8)).props("flat round")
        ui.button("Aujourd'hui", on_click=lambda: _reset_medium_term(self)).props("outline no-caps")
        ui.button(icon="chevron_right", on_click=lambda: _move_medium_term(self, 8)).props("flat round")
        ui.label(f"{window_start.strftime('%d/%m/%Y')} → {window_end.strftime('%d/%m/%Y')}").classes(
            "font-semibold ml-2"
        )

    if not efforts:
        with ui.card().classes("section-card w-full"):
            ui.label("Aucun effort moyen terme dans cette fenêtre.").classes("muted")
        return

    with ui.scroll_area().classes("w-full h-[calc(100vh-190px)]"):
        with ui.grid(columns=GANTT_WEEKS + 1).classes("gantt-grid gap-0"):
            with ui.column().classes("gantt-header p-2 justify-center"):
                ui.label("Projet / ressource").classes("font-semibold")
            for week in weeks:
                with ui.column().classes("gantt-header p-1 items-center justify-center"):
                    ui.label(week.strftime("%d %b")).classes("text-[10px] font-semibold")
            for effort_index, effort in enumerate(efforts):
                effort_row = int(effort.get("_row") or 0)
                total = _number(effort.get("Efforts Prévus"))
                detailed = _segment_hours_for_effort(self.repo, effort_row)
                remaining = max(total - detailed, 0.0)
                linked = _linked_demands(self.repo, effort_row)
                with ui.column().classes("gantt-label p-2 gap-0").on(
                    "click", lambda _, e=effort: _open_effort_macro_dialog(self, e)
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
                for week in weeks:
                    active = _gantt_overlap(effort, week, week + timedelta(days=6))
                    classes = "gantt-cell"
                    if active:
                        css = ui_module.PASTEL_CLASSES[effort_index % len(ui_module.PASTEL_CLASSES)]
                        classes += f" gantt-active {css}"
                    with ui.element("div").classes(classes):
                        if active:
                            ui.label(" ").classes("text-[9px]")


def _move_medium_term(self: ui_module.PlannerUI, weeks: int) -> None:
    start = getattr(self, "medium_term_start", week_start())
    self.medium_term_start = start + timedelta(weeks=weeks)
    self.render_content.refresh()


def _reset_medium_term(self: ui_module.PlannerUI) -> None:
    self.medium_term_start = week_start() - timedelta(weeks=2)
    self.render_content.refresh()


def _project_metadata(repo: ExcelRepository, number: Any) -> dict[str, Any]:
    target = _norm_project(number)
    return next(
        (
            project
            for project in repo.projects(active_only=False)
            if _norm_project(project.get("Numéro de Projet")) == target
        ),
        {},
    )


def _open_effort_macro_dialog(self: ui_module.PlannerUI, effort: dict[str, Any]) -> None:
    self.interaction_lock = True
    row = int(effort.get("_row") or 0)
    linked = _linked_demands(self.repo, row)
    total = _number(effort.get("Efforts Prévus"))
    detailed = _segment_hours_for_effort(self.repo, row)

    with ui.dialog() as dialog, ui.card().classes("w-[700px] max-w-full"):
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
        ui.label(f"Ressource pressentie : {effort.get('Équipe/Technicien attitré') or '—'}").classes(
            "text-sm"
        )
        if linked:
            ui.label(
                "Demandes liées : " + ", ".join(str(d.get("NoDemande") or "") for d in linked)
            ).classes("text-sm text-blue-700")
        else:
            ui.label("Aucune demande MO n'est encore liée à cet effort.").classes("text-sm muted")

        with ui.row().classes("w-full justify-end"):
            ui.button("Fermer", on_click=dialog.close).props("flat no-caps")
            if not linked:
                ui.button(
                    "Créer demande brouillon",
                    icon="note_add",
                    on_click=lambda: _create_demand_from_effort(self, effort, False, dialog),
                ).props("outline no-caps")
                ui.button(
                    "Créer et soumettre",
                    icon="send",
                    on_click=lambda: _create_demand_from_effort(self, effort, True, dialog),
                ).props("unelevated no-caps color=primary")
    dialog.on("hide", lambda _: self._unlock())
    dialog.open()


def _create_demand_from_effort(
    self: ui_module.PlannerUI,
    effort: dict[str, Any],
    submit: bool,
    dialog: Any,
) -> None:
    try:
        project = _project_metadata(self.repo, effort.get("N° projet"))
        technician = str(effort.get("Équipe/Technicien attitré") or "").strip()
        schedulable = {tech["name"] for tech in schedulable_technicians(self.repo)}
        payload = {
            "NumeroProjet": effort.get("N° projet"),
            "NomProjet": effort.get("Projet")
            or project.get("Nom de référence")
            or project.get("Description de l'appel d'offre")
            or "",
            "Client": project.get("Donneur d'ouvrage") or "",
            "ChargeProjet": effort.get("Chargé de projet")
            or project.get("Chargé de projet")
            or "",
            "TypeDemande": "Projet",
            "Priorite": "Normale",
            "DateDebutSouhaitee": effort.get("Date de début"),
            "DateFinSouhaitee": effort.get("Date de fin"),
            "Description": effort.get("Précision")
            or effort.get("Note")
            or effort.get("Compétence")
            or "Planification moyen terme",
            "NombreRessources": 1,
            "CompetencesRequises": effort.get("Compétence"),
            "TempsEstimeHeures": _number(effort.get("Efforts Prévus")),
            "TechnicienPropose": technician if technician in schedulable else None,
            SOURCE_EFFORT_FIELD: int(effort.get("_row") or 0),
        }
        number = self.repo.create_demand(payload, submit=submit)
        dialog.close()
        self._after_write(
            f"{number} {'soumise' if submit else 'créée comme brouillon'} depuis la planification moyen terme"
        )
    except Exception as exc:
        ui.notify(str(exc), type="negative")








def _demand_options(repo: ExcelRepository) -> dict[str, str]:
    options: dict[str, str] = {}
    for demand in repo.demands():
        if str(demand.get("Statut") or "") not in {"En planification", "Soumise", "À corriger"}:
            continue
        number = str(demand.get("NoDemande") or "")
        if number:
            options[number] = f"{number} — {demand.get('NumeroProjet') or '—'} · {demand.get('NomProjet') or ''}"
    return options


def _open_segment_dialog(
    self: ui_module.PlannerUI,
    segment: dict[str, Any] | None = None,
    demand_number: str | None = None,
) -> None:
    self.interaction_lock = True
    editing = segment is not None
    demands = {str(d.get("NoDemande") or ""): d for d in self.repo.demands()}
    selected_demand_number = str(segment.get("NoDemande") or "") if segment else str(demand_number or "")
    demand_options = _demand_options(self.repo)
    if selected_demand_number and selected_demand_number not in demand_options:
        demand = demands.get(selected_demand_number, {})
        demand_options[selected_demand_number] = (
            f"{selected_demand_number} — {demand.get('NumeroProjet') or '—'} · {demand.get('NomProjet') or ''}"
        )
    tech_options = [tech["name"] for tech in schedulable_technicians(self.repo)]
    current_demand = demands.get(selected_demand_number, {})
    effort_options = _effort_options(self.repo, current_demand.get("NumeroProjet") if current_demand else None)
    inherited_source = _source_effort_for_demand(current_demand) if current_demand else None
    source_value = None
    if segment and segment.get("SourceEffortRow") not in (None, ""):
        try:
            source_value = str(int(float(segment.get("SourceEffortRow"))))
        except (TypeError, ValueError):
            source_value = str(segment.get("SourceEffortRow"))
    else:
        source_value = inherited_source
    if source_value and source_value not in effort_options:
        effort_options.update(_effort_options(self.repo))

    with ui.dialog() as dialog, ui.card().classes("w-[760px] max-w-full"):
        ui.label(f"Modifier {segment.get('IDSegment')}" if editing else "Nouveau segment").classes(
            "text-xl font-bold"
        )
        demand_select = ui.select(
            demand_options,
            label="Demande MO",
            value=selected_demand_number or None,
            with_input=True,
            clearable=False,
        ).classes("w-full")
        if selected_demand_number:
            demand_select.props("readonly")

        technician = ui.select(
            tech_options,
            label="Technicien",
            value=segment.get("Technicien") if segment else current_demand.get("TechnicienPropose"),
            with_input=True,
            clearable=False,
        ).classes("w-full")

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
                value=_number(segment.get("HeuresPrevues")) if segment else None,
                min=0.5,
                step=0.5,
            ).classes("flex-1")

        with ui.row().classes("w-full"):
            status = ui.select(
                SEGMENT_STATUSES,
                label="Statut",
                value=str(segment.get("Statut") or "Planifié") if segment else "Planifié",
            ).classes("flex-1")
            source = ui.select(
                effort_options,
                label="Planification moyen terme liée (optionnel)",
                value=source_value,
                with_input=True,
                clearable=True,
            ).classes("flex-[2]")

        description = ui.input(
            "Description / précision",
            value=str(segment.get("Description") or "") if segment else str(current_demand.get("Description") or ""),
        ).classes("w-full")

        def get_demand() -> dict[str, Any]:
            return demands.get(str(demand_select.value or ""), {})

        def validate() -> bool:
            if not demand_select.value:
                ui.notify("Sélectionne une demande.", type="warning")
                return False
            if not technician.value:
                ui.notify("Sélectionne un technicien.", type="warning")
                return False
            start_date = _date_from_any(start.value)
            end_date = _date_from_any(end.value) or start_date
            if not start_date:
                ui.notify("La date de début est requise.", type="warning")
                return False
            if end_date and end_date < start_date:
                ui.notify("La date de fin ne peut pas précéder la date de début.", type="warning")
                return False
            if _number(hours.value) <= 0:
                ui.notify("Les heures prévues doivent être supérieures à zéro.", type="warning")
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
            return {
                "NoDemande": demand_select.value,
                "NumeroProjet": demand.get("NumeroProjet"),
                "NomProjet": demand.get("NomProjet"),
                "Technicien": technician.value,
                "DateDebut": start.value,
                "DateFin": end.value or start.value,
                "HeuresPrevues": hours.value,
                "Statut": status.value,
                "Description": description.value,
                "SourceEffortRow": source_row,
            }

        def capacity_in_window() -> float:
            start_date = _date_from_any(start.value)
            end_date = _date_from_any(end.value) or start_date
            if not start_date or not end_date or not technician.value:
                return 0.0
            capacity = 0.0
            cursor = start_date
            while cursor <= end_date:
                capacity += _availability_hours(self.repo, str(technician.value), cursor)
                cursor += timedelta(days=1)
            return capacity

        def save() -> None:
            if not validate():
                return
            try:
                capacity = capacity_in_window()
                if _number(hours.value) > capacity + 0.01:
                    ui.notify(
                        f"Attention : {_number(hours.value):g} h demandées pour {capacity:g} h de disponibilité brute "
                        "dans cette fenêtre. Le segment sera enregistré avec une surcharge.",
                        type="warning",
                        timeout=6000,
                    )
                if editing:
                    update_segment(self.repo, str(segment["IDSegment"]), payload())
                    message = f"{segment['IDSegment']} mis à jour"
                else:
                    ident = add_segment(self.repo, payload())
                    message = f"{ident} créé"
                dialog.close()
                self._after_write(message)
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        with ui.row().classes("w-full justify-end"):
            ui.button("Annuler", on_click=dialog.close).props("flat no-caps")
            if editing and str(segment.get("Statut") or "") != "Annulé":
                ui.button(
                    "Annuler le segment",
                    icon="cancel",
                    on_click=lambda: _cancel_segment(self, segment, dialog),
                ).props("flat no-caps color=negative")
            ui.button("Enregistrer", icon="save", on_click=save).props("unelevated no-caps color=primary")

    dialog.on("hide", lambda _: self._unlock())
    dialog.open()


def _cancel_segment(self: ui_module.PlannerUI, segment: dict[str, Any], dialog: Any) -> None:
    try:
        update_segment(self.repo, str(segment["IDSegment"]), {"Statut": "Annulé"})
        dialog.close()
        self._after_write(f"{segment['IDSegment']} annulé")
    except Exception as exc:
        ui.notify(str(exc), type="negative")




def install_v13_features() -> None:
    if getattr(ui_module.PlannerUI, "_v13_features_installed", False):
        return

    if SOURCE_EFFORT_FIELD not in DEMAND_HEADERS:
        DEMAND_HEADERS.append(SOURCE_EFFORT_FIELD)
    MASTER_SHEETS.add(SEGMENT_SHEET)

    original_ensure = ExcelRepository.ensure_app_sheets

    def ensure_app_sheets(self: ExcelRepository) -> None:
        original_ensure(self)
        _ensure_v13_sheets(self)

    ExcelRepository.ensure_app_sheets = ensure_app_sheets

    for index, item in enumerate(list(ui_module.NAV_ITEMS)):
        if item[0] == "planning":
            ui_module.NAV_ITEMS[index] = ("planning", "calendar_month", "Planning opérationnel")
            break
    if not any(item[0] == "medium_term" for item in ui_module.NAV_ITEMS):
        planning_index = next(
            (index for index, item in enumerate(ui_module.NAV_ITEMS) if item[0] == "planning"), 1
        )
        ui_module.NAV_ITEMS.insert(planning_index, ("medium_term", "timeline", "Planification moyen terme"))
    original_render_content = ui_module.PlannerUI._render_content
    original_page_sheets = ui_module.PlannerUI._page_sheets
    original_setup_style = ui_module.PlannerUI._setup_style

    def setup_style(self: ui_module.PlannerUI) -> None:
        original_setup_style(self)
        ui.add_head_html(
            """
            <style>
              .gantt-grid { width:100%; min-width:1700px; }
              .gantt-header { min-height:48px; background:#f8fafc; border:1px solid #e5e7eb; }
              .gantt-label { min-height:72px; background:white; border:1px solid #e5e7eb; cursor:pointer; min-width:290px; }
              .gantt-label:hover { background:#f8fafc; }
              .gantt-cell { min-height:72px; background:white; border:1px solid #e5e7eb; }
              .gantt-active { border-left-width:0 !important; border-radius:0 !important; opacity:.9; }
            </style>
            """
        )

    def render_content(self: ui_module.PlannerUI) -> None:
        if self.current_page == "medium_term":
            _render_medium_term(self)
            return
        original_render_content(self)

    def page_sheets(self: ui_module.PlannerUI) -> list[str]:
        if self.current_page == "planning":
            return [SEGMENT_SHEET, features.AVAILABILITY_SHEET, "DemandesMO"]
        if self.current_page == "medium_term":
            return ["Liste_Effort", "DemandesMO", SEGMENT_SHEET]
        if self.current_page == "dashboard":
            return [SEGMENT_SHEET, features.AVAILABILITY_SHEET, "DemandesMO"]
        return original_page_sheets(self)

    ui_module.PlannerUI._setup_style = setup_style
    ui_module.PlannerUI._render_content = render_content
    ui_module.PlannerUI._page_sheets = page_sheets
    ui_module.PlannerUI.render_dashboard = _render_dashboard_v13
    ui_module.PlannerUI.render_planning = _render_operational_planning
    ui_module.PlannerUI.render_medium_term = _render_medium_term
    ui_module.PlannerUI._v13_features_installed = True
