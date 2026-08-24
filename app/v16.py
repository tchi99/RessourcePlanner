from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from nicegui import ui

from . import features
from . import ui as ui_module
from . import v13, v14_engine, v15, v15_engine, v15_refinements
from .bugfixes import schedulable_technicians
from .excel_repository import ExcelRepository, _date_from_any
from .services import week_days, week_start


RESOURCE_CLASSES = [
    "Programmation",
    "Installation",
    "Monteur de panneau",
    "Dessinateur",
    "Gestion de projet",
]
UNCLASSIFIED = "Non classé"
ALL_CLASSES = "Toutes les classes"
ALL_RESOURCES = "Toutes les ressources"
ALL_PROJECTS = "Tous les projets"
ALL_CONFIRMATIONS = "Tous"


def _normalized_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    replacements = {
        "é": "e",
        "è": "e",
        "ê": "e",
        "ë": "e",
        "à": "a",
        "â": "a",
        "ä": "a",
        "î": "i",
        "ï": "i",
        "ô": "o",
        "ö": "o",
        "ù": "u",
        "û": "u",
        "ü": "u",
        "ç": "c",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return " ".join(text.split())


def _normalize_resource_class(value: Any) -> str | None:
    text = _normalized_text(value)
    if not text:
        return None
    if "programm" in text or "automatis" in text:
        return "Programmation"
    if "installation" in text or "installateur" in text:
        return "Installation"
    if "monteur" in text and "panneau" in text:
        return "Monteur de panneau"
    if "panel" in text and ("builder" in text or "wire" in text):
        return "Monteur de panneau"
    if "dessin" in text or "draft" in text or "cad" in text:
        return "Dessinateur"
    if "gestion" in text and "projet" in text:
        return "Gestion de projet"
    if "charge" in text and "projet" in text:
        return "Gestion de projet"
    if text in {_normalized_text(item) for item in RESOURCE_CLASSES}:
        return next(item for item in RESOURCE_CLASSES if _normalized_text(item) == text)
    return None


def _configuration_class_candidates(repo: ExcelRepository) -> dict[str, str]:
    """Lit prudemment une éventuelle colonne de classe associée aux ressources.

    Le classeur historique contient plusieurs tableaux côte à côte dans
    « Configuration des listes ». La description de la ressource demeure donc la
    source prioritaire. Une colonne explicite de classe n'est utilisée qu'en
    solution de repli lorsqu'elle contient une des cinq classes reconnues.
    """
    result: dict[str, str] = {}
    try:
        rows = repo._sheet_as_records("Configuration des listes", "Équipe/Technicien")
    except Exception:
        return result
    for row in rows:
        name = str(row.get("Équipe/Technicien") or "").strip()
        if not name or name.lower().startswith("team "):
            continue
        for header in (
            "Classe ressource",
            "Classe Ressource",
            "Classe employé",
            "Classe Employé",
            "Classe",
            "Classes",
        ):
            parsed = _normalize_resource_class(row.get(header))
            if parsed:
                result[name] = parsed
                break
    return result


def resource_class_map(repo: ExcelRepository) -> dict[str, str]:
    explicit = _configuration_class_candidates(repo)
    result: dict[str, str] = {}
    for tech in schedulable_technicians(repo):
        name = str(tech.get("name") or "").strip()
        # Description/Team sont prioritaires afin de ne pas associer par erreur une
        # valeur provenant d'un tableau indépendant placé sur la même ligne Excel.
        resource_class = (
            _normalize_resource_class(tech.get("description"))
            or _normalize_resource_class(tech.get("team"))
            or explicit.get(name)
            or UNCLASSIFIED
        )
        result[name] = resource_class
    return result


def _required_class(repo: ExcelRepository, segment: dict[str, Any]) -> str | None:
    competence = str(segment.get("CompetenceRequise") or "").strip()
    if competence:
        direct = _normalize_resource_class(competence)
        if direct:
            return direct
        try:
            expertise = repo.expertise_for_competency(competence)
        except Exception:
            expertise = None
        parsed = _normalize_resource_class(expertise)
        if parsed:
            return parsed
    return None


def _actual_allocations(repo: ExcelRepository) -> list[dict[str, Any]]:
    return [
        row
        for row in v15_engine.allocation_records(repo)
        if not v15_refinements.is_missing_allocation(row)
    ]


def _demand_lookup(repo: ExcelRepository) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("NoDemande") or ""): row
        for row in repo.demands()
        if row.get("NoDemande")
    }


def _capacity_between(repo: ExcelRepository, technician: str, start: date, end: date) -> float:
    total = 0.0
    cursor = start
    while cursor <= end:
        total += v13._availability_hours(repo, technician, cursor)
        cursor += timedelta(days=1)
    return round(total, 2)


def _resource_window_stats(
    repo: ExcelRepository,
    technician: str,
    start: date,
    end: date,
    *,
    exclude_segment_id: str | None = None,
    allocations: list[dict[str, Any]] | None = None,
    demands: dict[str, dict[str, Any]] | None = None,
) -> dict[str, float]:
    allocations = allocations if allocations is not None else _actual_allocations(repo)
    demands = demands if demands is not None else _demand_lookup(repo)
    capacity = _capacity_between(repo, technician, start, end)
    confirmed = 0.0
    tentative = 0.0
    overtime = 0.0

    for row in allocations:
        day = _date_from_any(row.get("Date"))
        if not day or day < start or day > end:
            continue
        if str(row.get("Technicien") or "").strip() != technician:
            continue
        if exclude_segment_id and str(row.get("IDSegment") or "") == exclude_segment_id:
            continue
        hours = v13._number(row.get("Heures"))
        if v15_engine._truthy(row.get("HorsHoraire")):
            overtime += hours
            continue
        demand = demands.get(str(row.get("NoDemande") or ""), {})
        if v15_refinements.demand_confirmation(demand) == "Tentative":
            tentative += hours
        else:
            confirmed += hours

    free_after_confirmed = max(capacity - confirmed, 0.0)
    prudent_free = max(capacity - confirmed - tentative, 0.0)
    return {
        "capacity": round(capacity, 2),
        "confirmed": round(confirmed, 2),
        "tentative": round(tentative, 2),
        "overtime": round(overtime, 2),
        "free_after_confirmed": round(free_after_confirmed, 2),
        "prudent_free": round(prudent_free, 2),
    }


def _weekly_resource_stats(
    repo: ExcelRepository,
    week: date,
) -> dict[str, dict[str, float]]:
    end = week + timedelta(days=6)
    allocations = _actual_allocations(repo)
    demands = _demand_lookup(repo)
    return {
        tech["name"]: _resource_window_stats(
            repo,
            tech["name"],
            week,
            end,
            allocations=allocations,
            demands=demands,
        )
        for tech in schedulable_technicians(repo)
    }


def recommend_resources(repo: ExcelRepository, segment: dict[str, Any]) -> list[dict[str, Any]]:
    start, end = v13._segment_dates(segment)
    if not start or not end:
        return []
    required = v13._number(segment.get("HeuresPrevues"))
    required_class = _required_class(repo, segment)
    class_map = resource_class_map(repo)
    allocations = _actual_allocations(repo)
    demands = _demand_lookup(repo)
    segment_id = str(segment.get("IDSegment") or "")
    rows: list[dict[str, Any]] = []

    for tech in schedulable_technicians(repo):
        name = str(tech.get("name") or "").strip()
        stats = _resource_window_stats(
            repo,
            name,
            start,
            end,
            exclude_segment_id=segment_id,
            allocations=allocations,
            demands=demands,
        )
        tech_class = class_map.get(name, UNCLASSIFIED)
        class_match = not required_class or tech_class == required_class
        enough_prudent = stats["prudent_free"] + 0.01 >= required
        enough_confirmed = stats["free_after_confirmed"] + 0.01 >= required
        overtime_needed = max(required - stats["prudent_free"], 0.0)

        score = 0.0
        if class_match:
            score += 10000
        if enough_prudent:
            score += 5000
        elif enough_confirmed:
            score += 2500
        score += min(stats["prudent_free"], required) * 10
        score -= stats["tentative"] * 2
        score -= overtime_needed * 8

        rows.append(
            {
                "name": name,
                "class": tech_class,
                "class_match": class_match,
                "required_class": required_class,
                "required": required,
                "score": score,
                "enough_prudent": enough_prudent,
                "enough_confirmed": enough_confirmed,
                "overtime_needed": round(overtime_needed, 2),
                **stats,
            }
        )

    rows.sort(
        key=lambda row: (
            -int(bool(row["class_match"])),
            -int(bool(row["enough_prudent"])),
            -row["score"],
            -row["prudent_free"],
            row["name"],
        )
    )
    return rows


def _assign_segment(self: ui_module.PlannerUI, segment: dict[str, Any], technician: str, dialog: Any) -> None:
    try:
        v13.update_segment(
            self.repo,
            str(segment.get("IDSegment") or ""),
            {"Technicien": technician, "Statut": "Planifié"},
        )
        summary = v15_refinements.rebuild_allocations_refined(self.repo)
        dialog.close()
        message = f"{segment.get('IDSegment')} assigné à {technician}"
        if summary.get("unallocated_hours", 0) > 0:
            message += f" · {summary['unallocated_hours']:g} h nécessitent du hors horaire"
        self._after_write(message)
    except Exception as exc:
        ui.notify(str(exc), type="negative")


def _open_recommendation_dialog(self: ui_module.PlannerUI, segment: dict[str, Any]) -> None:
    self.interaction_lock = True
    recommendations = recommend_resources(self.repo, segment)
    competence = str(segment.get("CompetenceRequise") or "Compétence non précisée")
    required_class = _required_class(self.repo, segment)
    start, end = v13._segment_dates(segment)

    with ui.dialog() as dialog, ui.card().classes("w-[920px] max-w-full"):
        ui.label("Trouver une ressource").classes("text-xl font-bold")
        ui.label(
            f"{segment.get('NumeroProjet') or '—'} · {segment.get('NomProjet') or ''} · "
            f"{v13._number(segment.get('HeuresPrevues')):g} h"
        ).classes("font-semibold")
        ui.label(
            f"Compétence : {competence} · Classe suggérée : {required_class or 'non déterminée'} · "
            f"Fenêtre : {start.strftime('%d/%m/%Y') if start else '—'} → {end.strftime('%d/%m/%Y') if end else '—'}"
        ).classes("text-sm muted")
        ui.label(
            "La capacité prudente soustrait les travaux confirmés et tentatifs. La capacité après confirmés permet de voir la marge qui redeviendrait disponible si les travaux tentatifs ne se réalisent pas."
        ).classes("text-xs muted")

        if not recommendations:
            ui.label("Aucune ressource planifiable trouvée.").classes("muted")
        else:
            for index, row in enumerate(recommendations):
                recommended = index == 0 and row["class_match"]
                border = "border:2px solid #16a34a;" if recommended else "border:1px solid #e5e7eb;"
                with ui.card().classes("w-full p-3").style(border):
                    with ui.row().classes("w-full items-center"):
                        with ui.column().classes("gap-0 flex-1"):
                            title = f"{row['name']} · {row['class']}"
                            if recommended:
                                title += " · Recommandé"
                            ui.label(title).classes("font-semibold")
                            match_text = (
                                "Classe compatible"
                                if row["class_match"]
                                else f"Classe différente de {row['required_class']}"
                            )
                            ui.label(match_text).classes(
                                "text-xs text-green-700" if row["class_match"] else "text-xs text-gray-500"
                            )
                            ui.label(
                                f"{row['prudent_free']:.1f} h libres prudentes · "
                                f"{row['free_after_confirmed']:.1f} h après confirmés · "
                                f"{row['tentative']:.1f} h tentatives"
                            ).classes("text-xs")
                            if row["overtime_needed"] > 0:
                                ui.label(
                                    f"Environ {row['overtime_needed']:.1f} h ne tiennent pas dans la capacité prudente."
                                ).classes("text-xs text-orange-700")
                        ui.button(
                            "Assigner",
                            icon="person_add",
                            on_click=lambda tech=row["name"]: _assign_segment(
                                self, segment, tech, dialog
                            ),
                        ).props("unelevated no-caps color=primary")

        with ui.row().classes("w-full justify-end"):
            ui.button("Fermer", on_click=dialog.close).props("flat no-caps")

    dialog.on("hide", lambda _: self._unlock())
    dialog.open()


def _filter_value(self: ui_module.PlannerUI, name: str, default: Any) -> Any:
    return getattr(self, name, default)


def _set_planning_filter(self: ui_module.PlannerUI, name: str, value: Any) -> None:
    setattr(self, name, value)
    self.render_content.refresh()


def _project_number_for_allocation(allocation: dict[str, Any]) -> str:
    return str(allocation.get("NumeroProjet") or "").strip()


def _resource_group_order(group_name: str) -> int:
    try:
        return RESOURCE_CLASSES.index(group_name)
    except ValueError:
        return len(RESOURCE_CLASSES)


def _render_resource_row(
    self: ui_module.PlannerUI,
    tech: dict[str, Any],
    days: list[date],
    allocations: list[dict[str, Any]],
    segments: dict[str, dict[str, Any]],
    demands: dict[str, dict[str, Any]],
    pending: list[dict[str, Any]],
    week_stats: dict[str, dict[str, float]],
    project_filter: str,
    confirmation_filter: str,
) -> None:
    name = tech["name"]
    stats = week_stats.get(name, {})
    with ui.column().classes("resource-cell p-3 justify-center gap-1"):
        ui.label(name).classes("font-semibold")
        ui.label(
            f"{stats.get('prudent_free', 0):.1f} h libres / {stats.get('capacity', 0):.1f} h"
        ).classes("text-xs text-green-700")
        if stats.get("tentative", 0) > 0:
            ui.label(f"{stats['tentative']:.1f} h tentatives").classes("text-[10px] text-amber-700")

    for day in days:
        state = features.availability_for_day(self.repo, name, day)
        day_capacity = v13._availability_hours(self.repo, name, day)
        day_allocations = [
            row
            for row in allocations
            if str(row.get("Technicien") or "").strip() == name
            and row.get("Date") == day
            and (project_filter == ALL_PROJECTS or _project_number_for_allocation(row) == project_filter)
        ]
        if confirmation_filter != ALL_CONFIRMATIONS:
            day_allocations = [
                row
                for row in day_allocations
                if v15_refinements.demand_confirmation(
                    demands.get(str(row.get("NoDemande") or ""), {})
                )
                == confirmation_filter
            ]
        actual_allocations = [
            row for row in day_allocations if not v15_refinements.is_missing_allocation(row)
        ]
        pending_day = [
            row
            for row in pending
            if str(row.get("TechnicienPropose") or "").strip() == name
            and v15._pending_covers_day(row, day)
            and v13._availability_hours(self.repo, name, day) > 0
            and (project_filter == ALL_PROJECTS or str(row.get("NumeroProjet") or "") == project_filter)
            and (
                confirmation_filter == ALL_CONFIRMATIONS
                or v15_refinements.demand_confirmation(row) == confirmation_filter
            )
        ]
        planned = sum(v13._number(row.get("Heures")) for row in actual_allocations)
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
                css = "text-[10px] text-red-700 font-semibold" if overloaded else "text-[10px] muted"
                ui.label(f"{planned:.1f}/{day_capacity:.1f} h").classes(css)

            for allocation in day_allocations:
                segment = segments.get(str(allocation.get("IDSegment") or ""), {})
                demand = demands.get(str(allocation.get("NoDemande") or ""), {})
                style, label = v15_refinements._allocation_style(allocation, demand, overloaded)
                with ui.element("div").classes("shift-card").style(style).on(
                    "click",
                    lambda _, a=allocation: v15_refinements._open_allocation_dialog(
                        self, allocation=a
                    ),
                ):
                    ui.label(
                        f"{allocation.get('NumeroProjet') or '—'} · {allocation.get('NomProjet') or ''}"
                    ).classes("text-xs font-semibold")
                    ui.label(
                        str(segment.get("Description") or allocation.get("IDSegment") or "Allocation")
                    ).classes("text-xs")
                    suffix = " · 🔒" if v15_engine._truthy(allocation.get("Verrouillee")) else ""
                    if v15_refinements.demand_confirmation(demand) == "Tentative" and "Tentative" not in label:
                        label = f"Tentative · {label}"
                    ui.label(
                        f"{v13._number(allocation.get('Heures')):.1f} h · {label}{suffix}"
                    ).classes("text-[11px] muted")

            for demand in pending_day:
                tentative = v15_refinements.demand_confirmation(demand) == "Tentative"
                style = (
                    "background:#fffbeb;border:2px dashed #d97706;opacity:.95;"
                    if tentative
                    else "background:#f3f4f6;border:2px dashed #9ca3af;opacity:.9;"
                )
                with ui.element("div").classes("shift-card").style(style):
                    ui.label(
                        f"{demand.get('NumeroProjet') or '—'} · {demand.get('NomProjet') or ''}"
                    ).classes("text-xs font-semibold")
                    ui.label(str(demand.get("Description") or "")).classes("text-xs")
                    ui.label(
                        f"{v15_refinements.demand_confirmation(demand)} · en attente d'approbation · 0 h"
                    ).classes("text-[11px] text-gray-600")


def _render_planning_v16(self: ui_module.PlannerUI) -> None:
    days = week_days(self.current_week)
    techs = schedulable_technicians(self.repo)
    class_map = resource_class_map(self.repo)
    week_stats = _weekly_resource_stats(self.repo, self.current_week)
    demands = _demand_lookup(self.repo)
    segments = {
        str(row.get("IDSegment") or ""): row
        for row in v13.segment_records(self.repo, include_cancelled=False)
    }
    allocations = [
        row
        for row in v15_engine.allocation_records(self.repo)
        if row.get("Date") and days[0] <= row["Date"] <= days[-1]
    ]
    unassigned = v15._unassigned_segments_for_week(self.repo, self.current_week)
    pending = v15._pending_demands_for_week(self.repo, self.current_week)

    class_filter = _filter_value(self, "planning_class_filter", ALL_CLASSES)
    resource_filter = _filter_value(self, "planning_resource_filter", ALL_RESOURCES)
    project_filter = _filter_value(self, "planning_project_filter", ALL_PROJECTS)
    confirmation_filter = _filter_value(self, "planning_confirmation_filter", ALL_CONFIRMATIONS)
    only_available = bool(_filter_value(self, "planning_only_available", False))

    project_values = sorted(
        {
            str(row.get("NumeroProjet") or "").strip()
            for row in [*allocations, *unassigned, *pending]
            if str(row.get("NumeroProjet") or "").strip()
        }
    )

    with ui.row().classes("w-full items-center"):
        with ui.column().classes("gap-0"):
            ui.label("Planning opérationnel").classes("text-2xl font-bold")
            ui.label(
                "Ressources regroupées par classe : Programmation / Installation / Monteur de panneau / Dessinateur / Gestion de projet."
            ).classes("muted")
        ui.space()
        ui.button(
            "Quart manuel",
            icon="add_task",
            on_click=lambda: v15_refinements._open_allocation_dialog(self),
        ).props("outline no-caps")
        ui.button(
            "Recalculer",
            icon="calculate",
            on_click=lambda: v15_refinements._recalculate(self),
        ).props("outline no-caps")
        ui.button(icon="chevron_left", on_click=self.previous_week).props("flat round")
        ui.button("Aujourd'hui", on_click=self.today_week).props("outline no-caps")
        ui.button(icon="chevron_right", on_click=self.next_week).props("flat round")
        ui.label(f"{days[0].strftime('%d %b')} – {days[-1].strftime('%d %b %Y')}").classes(
            "font-semibold ml-2"
        )

    with ui.card().classes("section-card w-full"):
        with ui.row().classes("w-full items-end gap-3"):
            ui.select(
                [ALL_CLASSES, *RESOURCE_CLASSES, UNCLASSIFIED],
                label="Classe",
                value=class_filter,
                on_change=lambda event: _set_planning_filter(
                    self, "planning_class_filter", event.value
                ),
            ).classes("min-w-[190px]")
            ui.select(
                [ALL_RESOURCES, *sorted(tech["name"] for tech in techs)],
                label="Ressource",
                value=resource_filter,
                with_input=True,
                on_change=lambda event: _set_planning_filter(
                    self, "planning_resource_filter", event.value
                ),
            ).classes("min-w-[210px]")
            ui.select(
                [ALL_PROJECTS, *project_values],
                label="Projet",
                value=project_filter,
                with_input=True,
                on_change=lambda event: _set_planning_filter(
                    self, "planning_project_filter", event.value
                ),
            ).classes("min-w-[180px]")
            ui.select(
                [ALL_CONFIRMATIONS, "Confirmée", "Tentative"],
                label="Confirmation",
                value=confirmation_filter,
                on_change=lambda event: _set_planning_filter(
                    self, "planning_confirmation_filter", event.value
                ),
            ).classes("min-w-[160px]")
            ui.checkbox(
                "Seulement avec capacité",
                value=only_available,
                on_change=lambda event: _set_planning_filter(
                    self, "planning_only_available", event.value
                ),
            )

    visible_unassigned = [
        segment
        for segment in unassigned
        if (project_filter == ALL_PROJECTS or str(segment.get("NumeroProjet") or "") == project_filter)
        and (
            confirmation_filter == ALL_CONFIRMATIONS
            or v15_refinements.demand_confirmation(
                demands.get(str(segment.get("NoDemande") or ""), {})
            )
            == confirmation_filter
        )
    ]
    if visible_unassigned:
        with ui.card().classes("section-card w-full"):
            ui.label(f"Travaux à planifier cette semaine ({len(visible_unassigned)})").classes(
                "text-lg font-semibold"
            )
            with ui.row().classes("w-full gap-2 flex-wrap"):
                for segment in visible_unassigned[:20]:
                    competence = v14_engine.segment_competence(segment, demands) or "Compétence non précisée"
                    required_class = _required_class(self.repo, segment)
                    with ui.card().classes("p-3 min-w-[280px] max-w-[370px]"):
                        ui.label(
                            f"{segment.get('NumeroProjet') or '—'} · {segment.get('NomProjet') or ''}"
                        ).classes("text-sm font-semibold")
                        ui.label(str(segment.get("Description") or "")).classes("text-xs")
                        ui.label(
                            f"{competence} · {required_class or 'Classe non déterminée'} · "
                            f"{v13._number(segment.get('HeuresPrevues')):g} h"
                        ).classes("text-xs text-orange-700")
                        with ui.row().classes("gap-1"):
                            ui.button(
                                "Trouver une ressource",
                                icon="recommend",
                                on_click=lambda s=segment: _open_recommendation_dialog(self, s),
                            ).props("unelevated dense no-caps color=primary")
                            ui.button(
                                "Segment",
                                icon="view_timeline",
                                on_click=lambda s=segment: v15_refinements._segment_dialog(
                                    self, segment=s
                                ),
                            ).props("flat dense no-caps")

    visible_pending = [
        demand
        for demand in pending
        if (project_filter == ALL_PROJECTS or str(demand.get("NumeroProjet") or "") == project_filter)
        and (
            confirmation_filter == ALL_CONFIRMATIONS
            or v15_refinements.demand_confirmation(demand) == confirmation_filter
        )
    ]
    if visible_pending:
        with ui.card().classes("section-card w-full"):
            ui.label(f"En attente d'approbation dans cette semaine ({len(visible_pending)})").classes(
                "text-lg font-semibold"
            )
            ui.label("Ces besoins sont visibles, mais comptent 0 h de charge.").classes("text-xs muted")
            with ui.row().classes("w-full gap-2 flex-wrap"):
                for demand in visible_pending[:20]:
                    tentative = v15_refinements.demand_confirmation(demand) == "Tentative"
                    style = (
                        "background:#fffbeb;border:2px dashed #d97706;"
                        if tentative
                        else "background:#f9fafb;border:1px dashed #9ca3af;"
                    )
                    with ui.card().classes("p-3 min-w-[250px] max-w-[340px]").style(style):
                        ui.label(
                            f"{demand.get('NumeroProjet') or '—'} · {demand.get('NomProjet') or ''}"
                        ).classes("text-sm font-semibold")
                        ui.label(
                            f"{v15_refinements.demand_confirmation(demand)} · "
                            f"{demand.get('CompetencesRequises') or 'Compétence non précisée'}"
                        ).classes("text-xs")
                        ui.label(
                            f"{self._date_text(demand.get('DateDebutSouhaitee'))} → "
                            f"{self._date_text(demand.get('DateFinSouhaitee'))}"
                        ).classes("text-xs muted")

    filtered_techs = []
    for tech in techs:
        name = tech["name"]
        group = class_map.get(name, UNCLASSIFIED)
        if class_filter != ALL_CLASSES and group != class_filter:
            continue
        if resource_filter != ALL_RESOURCES and name != resource_filter:
            continue
        if only_available and week_stats.get(name, {}).get("prudent_free", 0) <= 0.01:
            continue
        filtered_techs.append(tech)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for tech in filtered_techs:
        group = class_map.get(tech["name"], UNCLASSIFIED)
        grouped.setdefault(group, []).append(tech)
    for group in grouped:
        grouped[group].sort(
            key=lambda tech: (
                -week_stats.get(tech["name"], {}).get("prudent_free", 0.0),
                tech["name"],
            )
        )

    if not grouped:
        with ui.card().classes("section-card w-full"):
            ui.label("Aucune ressource ne correspond aux filtres.").classes("muted")
        return

    with ui.scroll_area().classes("w-full h-[calc(100vh-360px)]"):
        for group_name in sorted(grouped, key=_resource_group_order):
            group_techs = grouped[group_name]
            total_free = sum(
                week_stats.get(tech["name"], {}).get("prudent_free", 0.0)
                for tech in group_techs
            )
            total_capacity = sum(
                week_stats.get(tech["name"], {}).get("capacity", 0.0)
                for tech in group_techs
            )
            with ui.expansion(
                f"{group_name} · {len(group_techs)} ressource(s) · {total_free:.1f} h libres / {total_capacity:.1f} h",
                icon="groups",
                value=True,
            ).classes("w-full"):
                with ui.grid(columns=8).classes("schedule-grid gap-0 w-full"):
                    with ui.column().classes("day-header p-3 justify-center"):
                        ui.label("Ressource").classes("font-semibold")
                    for day in days:
                        with ui.column().classes("day-header p-2 items-center justify-center"):
                            ui.label(day.strftime("%a").capitalize()).classes("text-xs uppercase muted")
                            ui.label(day.strftime("%d")).classes("text-xl font-semibold")
                    for tech in group_techs:
                        _render_resource_row(
                            self,
                            tech,
                            days,
                            allocations,
                            segments,
                            demands,
                            pending,
                            week_stats,
                            project_filter,
                            confirmation_filter,
                        )


def _render_class_capacity_card(self: ui_module.PlannerUI) -> None:
    selected_week = getattr(self, "dashboard_week", week_start())
    stats = _weekly_resource_stats(self.repo, selected_week)
    classes = resource_class_map(self.repo)
    grouped: dict[str, dict[str, float]] = {}
    for name, values in stats.items():
        group = classes.get(name, UNCLASSIFIED)
        bucket = grouped.setdefault(
            group,
            {"capacity": 0.0, "confirmed": 0.0, "tentative": 0.0, "free": 0.0, "resources": 0.0},
        )
        bucket["capacity"] += values["capacity"]
        bucket["confirmed"] += values["confirmed"]
        bucket["tentative"] += values["tentative"]
        bucket["free"] += values["prudent_free"]
        bucket["resources"] += 1

    with ui.card().classes("section-card w-full"):
        ui.label("Capacité par classe — semaine sélectionnée").classes("text-lg font-semibold")
        ui.label(
            "Capacité prudente = horaire standard − charge confirmée − charge tentative."
        ).classes("text-xs muted")
        if not grouped:
            ui.label("Aucune ressource planifiable.").classes("muted")
            return
        for group_name in sorted(grouped, key=_resource_group_order):
            row = grouped[group_name]
            with ui.row().classes("w-full items-center border-b border-gray-100 py-2"):
                with ui.column().classes("gap-0 min-w-[210px]"):
                    ui.label(group_name).classes("font-medium")
                    ui.label(f"{int(row['resources'])} ressource(s)").classes("text-xs muted")
                ui.space()
                ui.label(
                    f"{row['confirmed']:.1f} h confirmées · {row['tentative']:.1f} h tentatives · "
                    f"{row['free']:.1f} h libres / {row['capacity']:.1f} h"
                ).classes("text-sm")


def install_v16_features() -> None:
    if getattr(ui_module.PlannerUI, "_v16_features_installed", False):
        return

    previous_dashboard = ui_module.PlannerUI.render_dashboard

    def render_dashboard_v16(self: ui_module.PlannerUI) -> None:
        previous_dashboard(self)
        _render_class_capacity_card(self)

    # Le renderer V1.6 reste une fonction explicite consommée par v16_refinements;
    # l'installer conserve uniquement son extension du dashboard.
    ui_module.PlannerUI.render_dashboard = render_dashboard_v16
    ui_module.PlannerUI._v16_features_installed = True
