from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from nicegui import ui

from . import ui as ui_module
from .bugfixes import schedulable_technicians
from .excel_repository import ExcelRepository, _date_from_any
from . import v13
from .services import week_start


GANTT_COLORS = [
    "#dbeafe",
    "#dcfce7",
    "#fef3c7",
    "#fce7f3",
    "#ede9fe",
    "#cffafe",
    "#ffedd5",
    "#e0e7ff",
]


def _estimated_segment_hours(repo: ExcelRepository, demand: dict[str, Any], technician: str) -> float:
    hours = v13._number(demand.get("TempsEstimeHeures"))
    if hours > 0:
        return hours

    source = demand.get(v13.SOURCE_EFFORT_FIELD)
    if source not in (None, ""):
        try:
            source_row = int(float(source))
        except (TypeError, ValueError):
            source_row = None
        if source_row:
            effort = next(
                (row for row in repo.efforts(include_closed=False) if int(row.get("_row") or 0) == source_row),
                None,
            )
            if effort:
                effort_hours = v13._number(effort.get("Efforts Prévus"))
                if effort_hours > 0:
                    return effort_hours

    start = _date_from_any(demand.get("DateDebutSouhaitee"))
    end = _date_from_any(demand.get("DateFinSouhaitee")) or start
    days_estimate = v13._number(demand.get("TempsEstimeJours"))

    if technician and start and end:
        capacities: list[float] = []
        cursor = start
        while cursor <= end:
            capacity = v13._availability_hours(repo, technician, cursor)
            if capacity > 0:
                capacities.append(capacity)
            cursor += timedelta(days=1)

        if days_estimate > 0 and capacities:
            average_day = sum(capacities) / len(capacities)
            return round(days_estimate * average_day, 2)
        if capacities:
            return round(sum(capacities), 2)

    return 0.0


def _ensure_initial_segment(repo: ExcelRepository, demand: dict[str, Any]) -> str | None:
    number = str(demand.get("NoDemande") or "").strip()
    if not number or str(demand.get("Statut") or "") != "En planification":
        return None

    existing = [
        row
        for row in v13.segment_records(repo, include_cancelled=False)
        if str(row.get("NoDemande") or "").strip() == number
    ]
    if existing:
        return None

    schedulable = {tech["name"] for tech in schedulable_technicians(repo)}
    proposed = str(demand.get("TechnicienPropose") or "").strip()
    technician = proposed if proposed in schedulable else ""
    status = "Planifié" if technician else "À assigner"

    source: Any = demand.get(v13.SOURCE_EFFORT_FIELD)
    if source not in (None, ""):
        try:
            source = int(float(source))
        except (TypeError, ValueError):
            pass

    return v13.add_segment(
        repo,
        {
            "NoDemande": number,
            "NumeroProjet": demand.get("NumeroProjet"),
            "NomProjet": demand.get("NomProjet"),
            "Technicien": technician or None,
            "DateDebut": demand.get("DateDebutSouhaitee"),
            "DateFin": demand.get("DateFinSouhaitee") or demand.get("DateDebutSouhaitee"),
            "HeuresPrevues": _estimated_segment_hours(repo, demand, technician),
            "Statut": status,
            "Description": demand.get("Description") or "Segment initial créé à l'approbation",
            "SourceEffortRow": source,
        },
    )


def _backfill_approved_demands(repo: ExcelRepository) -> int:
    created = 0
    for demand in repo.demands():
        if str(demand.get("Statut") or "") != "En planification":
            continue
        if _ensure_initial_segment(repo, demand):
            created += 1
    return created


def _render_medium_term_fixed(self: ui_module.PlannerUI) -> None:
    if not hasattr(self, "medium_term_start"):
        self.medium_term_start = week_start() - timedelta(weeks=2)

    window_start: date = self.medium_term_start
    weeks = [window_start + timedelta(weeks=index) for index in range(v13.GANTT_WEEKS)]
    window_end = weeks[-1] + timedelta(days=6)
    efforts = [
        effort
        for effort in self.repo.efforts(include_closed=False)
        if v13._gantt_overlap(effort, window_start, window_end)
    ]

    with ui.row().classes("w-full items-center"):
        with ui.column().classes("gap-0"):
            ui.label("Planification moyen terme").classes("text-2xl font-bold")
            ui.label(
                "Vue macro de Liste_Effort. Une barre représente une fenêtre de besoin, pas un quart de travail."
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
                with ui.column().classes("gantt-header p-1 items-center justify-center"):
                    ui.label(week.strftime("%d %b")).classes("text-[10px] font-semibold")

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

                color = GANTT_COLORS[effort_index % len(GANTT_COLORS)]
                for week in weeks:
                    active = v13._gantt_overlap(effort, week, week + timedelta(days=6))
                    cell = ui.element("div").classes("gantt-cell gantt-active" if active else "gantt-cell")
                    if active:
                        cell.style(f"background-color:{color} !important; border-color:#cbd5e1;")


def install_v13_fixes() -> None:
    if getattr(v13, "_v13_fixes_installed", False):
        return

    if "À assigner" not in v13.SEGMENT_STATUSES:
        v13.SEGMENT_STATUSES.insert(0, "À assigner")

    original_approve = ExcelRepository.approve_demand

    def approve_demand(self: ExcelRepository, number: str, comment: str = "") -> None:
        original_approve(self, number, comment)
        demand = next(
            (row for row in self.demands() if str(row.get("NoDemande") or "") == str(number)),
            None,
        )
        if not demand:
            return
        try:
            _ensure_initial_segment(self, demand)
        except Exception as exc:
            raise RuntimeError(
                f"La demande {number} a été approuvée, mais le segment initial n'a pas pu être créé : {exc}"
            ) from exc

    ExcelRepository.approve_demand = approve_demand

    original_ensure = ExcelRepository.ensure_app_sheets

    def ensure_app_sheets(self: ExcelRepository) -> None:
        original_ensure(self)
        _backfill_approved_demands(self)

    ExcelRepository.ensure_app_sheets = ensure_app_sheets

    v13._render_medium_term = _render_medium_term_fixed
    ui_module.PlannerUI.render_medium_term = _render_medium_term_fixed
    v13._v13_fixes_installed = True
