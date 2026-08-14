from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from nicegui import ui

from . import ui as ui_module
from . import v13, v15_engine, v16, v16_refinements, v18
from .bugfixes import schedulable_technicians
from .excel_repository import ExcelRepository, _as_matrix, _date_from_any


SORT_OPTIONS = {
    "start_asc": "Date de début ↑",
    "start_desc": "Date de début ↓",
    "end_asc": "Date de fin ↑",
    "end_desc": "Date de fin ↓",
    "project_asc": "Numéro de projet ↑",
    "project_desc": "Numéro de projet ↓",
    "manager_asc": "Chargé de projet A → Z",
    "manager_desc": "Chargé de projet Z → A",
    "hours_asc": "Effort prévu ↑",
    "hours_desc": "Effort prévu ↓",
}


def _selection(value: Any, all_token: str | None = None) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, (list, tuple, set)):
        values = [str(item).strip() for item in value if str(item or "").strip()]
    else:
        values = [str(value).strip()]
    if all_token:
        values = [item for item in values if item != all_token]
    return values


def _validated_selection(value: Any, choices: set[str], all_token: str | None = None) -> list[str]:
    return [item for item in _selection(value, all_token) if item in choices]


def _set_multi_filter(self: ui_module.PlannerUI, name: str, value: Any) -> None:
    setattr(self, name, _selection(value))
    self.render_content.refresh()


def _matches_multi(
    effort: dict[str, Any],
    linked: list[dict[str, Any]],
    *,
    projects: set[str],
    managers: set[str],
    resource_classes: set[str],
    technicians: set[str],
    competencies: set[str],
    statuses: set[str],
    class_map: dict[str, str],
) -> bool:
    if projects and str(effort.get("N° projet") or "").strip() not in projects:
        return False
    if managers and str(effort.get("Chargé de projet") or "").strip() not in managers:
        return False
    if statuses and str(effort.get("Status") or "").strip() not in statuses:
        return False

    effort_tech = str(effort.get("Équipe/Technicien attitré") or "").strip()
    linked_techs = {
        str(segment.get("Technicien") or "").strip()
        for segment in linked
        if str(segment.get("Technicien") or "").strip()
    }
    all_techs = linked_techs | ({effort_tech} if effort_tech else set())
    if technicians and not (all_techs & technicians):
        return False
    if resource_classes:
        present_classes = {
            class_map.get(name, v16.UNCLASSIFIED)
            for name in all_techs
        }
        if not (present_classes & resource_classes):
            return False

    if competencies:
        wanted = {v18._norm(value) for value in competencies}
        present = {v18._norm(effort.get("Compétence"))}
        present.update(v18._norm(segment.get("CompetenceRequise")) for segment in linked)
        if not (wanted & present):
            return False

    return True


def _sort_value(effort: dict[str, Any], mode: str) -> Any:
    if mode.startswith("start_"):
        return _date_from_any(effort.get("Date de début")) or date.max
    if mode.startswith("end_"):
        return _date_from_any(effort.get("Date de fin")) or date.max
    if mode.startswith("project_"):
        return v18._norm(effort.get("N° projet"))
    if mode.startswith("manager_"):
        return v18._norm(effort.get("Chargé de projet"))
    if mode.startswith("hours_"):
        return v13._number(effort.get("Efforts Prévus"))
    return _date_from_any(effort.get("Date de début")) or date.max


def _sort_descending(mode: str) -> bool:
    return str(mode).endswith("_desc")


def _render_capacity_heatmap_multi(
    self: ui_module.PlannerUI,
    weeks: list[date],
    class_map: dict[str, str],
    selected_classes: set[str],
) -> None:
    techs = [row["name"] for row in schedulable_technicians(self.repo)]
    allocations = v16._actual_allocations(self.repo)
    classes = list(v16.RESOURCE_CLASSES)
    if any(class_map.get(name, v16.UNCLASSIFIED) == v16.UNCLASSIFIED for name in techs):
        classes.append(v16.UNCLASSIFIED)
    if selected_classes:
        classes = [item for item in classes if item in selected_classes]

    with ui.expansion("Capacité par classe", icon="monitoring", value=True).classes(
        "w-full section-card"
    ):
        ui.label(
            "Charge détaillée totale (confirmée + tentative) comparée à la capacité standard. "
            "Les filtres de projet n'allègent pas cette charge afin de conserver la vue de capacité réelle."
        ).classes("text-xs muted mb-2")

        with ui.element("div").classes("v18-capacity-scroll"):
            with ui.element("div").classes("v18-capacity-grid"):
                ui.label("Classe").classes("v18-sticky v18-capacity-label font-semibold")
                for week in weeks:
                    ui.label(week.strftime("%d/%m")).classes(
                        "text-[10px] text-center font-semibold py-1"
                    )

                for class_name in classes:
                    names = [
                        name
                        for name in techs
                        if class_map.get(name, v16.UNCLASSIFIED) == class_name
                    ]
                    ui.label(class_name).classes(
                        "v18-sticky v18-capacity-label text-xs font-medium"
                    )
                    for week in weeks:
                        week_end = week + timedelta(days=6)
                        capacity = 0.0
                        load = 0.0
                        for name in names:
                            cursor = week
                            while cursor <= week_end:
                                capacity += v13._availability_hours(self.repo, name, cursor)
                                cursor += timedelta(days=1)
                        for allocation in allocations:
                            day = _date_from_any(allocation.get("Date"))
                            if (
                                day
                                and week <= day <= week_end
                                and str(allocation.get("Technicien") or "").strip() in names
                            ):
                                load += v13._number(allocation.get("Heures"))

                        pct = round(load / capacity * 100) if capacity else None
                        if pct is None:
                            style = "background:#f3f4f6;color:#6b7280;"
                            text = "—"
                        elif pct > 100:
                            style = "background:#fee2e2;color:#991b1b;"
                            text = f"{pct}%"
                        elif pct >= 85:
                            style = "background:#fef3c7;color:#92400e;"
                            text = f"{pct}%"
                        else:
                            style = "background:#dcfce7;color:#166534;"
                            text = f"{pct}%"
                        ui.label(text).classes(
                            "text-[10px] text-center rounded py-1 mx-[1px]"
                        ).style(style).tooltip(
                            f"{class_name} · semaine du {week.strftime('%d/%m/%Y')} · "
                            f"{load:.1f} h / {capacity:.1f} h"
                        )


def _render_medium_term_refined(self: ui_module.PlannerUI) -> None:
    v18.ensure_v18_schema(self.repo)
    if not hasattr(self, "medium_term_start"):
        self.medium_term_start = v18.week_start() - timedelta(weeks=2)

    window_start: date = self.medium_term_start
    weeks = [window_start + timedelta(weeks=index) for index in range(v18.GANTT_WEEKS)]
    window_end = weeks[-1] + timedelta(days=6)

    efforts = [
        effort
        for effort in self.repo.efforts(include_closed=False)
        if v18._overlap(
            _date_from_any(effort.get("Date de début")),
            _date_from_any(effort.get("Date de fin")),
            window_start,
            window_end,
        )
    ]
    segments = v13.segment_records(self.repo, include_cancelled=False)
    demands = {
        str(row.get("NoDemande") or ""): row
        for row in self.repo.demands()
        if row.get("NoDemande")
    }
    class_map = v16_refinements.resource_class_map(self.repo)

    linked_by_effort: dict[str, list[dict[str, Any]]] = {}
    for effort in efforts:
        identifier = str(effort.get(v18.EFFORT_ID_FIELD) or "")
        linked_by_effort[identifier] = v18._linked_segments(self.repo, effort, segments, demands)

    project_options: dict[str, str] = {}
    for effort in efforts:
        number = str(effort.get("N° projet") or "").strip()
        name = str(effort.get("Projet") or "").strip()
        if number:
            project_options[number] = f"{number} — {name}" if name else number

    managers = sorted(
        {
            str(effort.get("Chargé de projet") or "").strip()
            for effort in efforts
            if str(effort.get("Chargé de projet") or "").strip()
        },
        key=v18._norm,
    )
    technicians = sorted(
        {
            str(row.get("name") or "").strip()
            for row in schedulable_technicians(self.repo)
            if str(row.get("name") or "").strip()
        },
        key=v18._norm,
    )
    competencies = sorted(
        {
            str(effort.get("Compétence") or "").strip()
            for effort in efforts
            if str(effort.get("Compétence") or "").strip()
        }
        | {
            str(segment.get("CompetenceRequise") or "").strip()
            for segment in segments
            if str(segment.get("CompetenceRequise") or "").strip()
        },
        key=v18._norm,
    )
    statuses = sorted(
        {
            str(effort.get("Status") or "").strip()
            for effort in efforts
            if str(effort.get("Status") or "").strip()
        },
        key=v18._norm,
    )

    projects = _validated_selection(
        getattr(self, "v18_project", []), set(project_options), v18.ALL_PROJECTS
    )
    selected_managers = _validated_selection(
        getattr(self, "v18_manager", []), set(managers), v18.ALL_PROJECT_MANAGERS
    )
    selected_classes = _validated_selection(
        getattr(self, "v18_class", []),
        {*v16.RESOURCE_CLASSES, v16.UNCLASSIFIED},
        v18.ALL_CLASSES,
    )
    selected_technicians = _validated_selection(
        getattr(self, "v18_technician", []), set(technicians), v18.ALL_TECHNICIANS
    )
    selected_competencies = _validated_selection(
        getattr(self, "v18_competency", []), set(competencies), v18.ALL_COMPETENCIES
    )
    selected_statuses = _validated_selection(
        getattr(self, "v18_status", []), set(statuses), v18.ALL_STATUSES
    )
    group_by_manager = bool(getattr(self, "v18_group_manager", True))
    sort_mode = str(getattr(self, "v18_sort_mode", "start_asc") or "start_asc")
    if sort_mode not in SORT_OPTIONS:
        sort_mode = "start_asc"

    self.v18_project = projects
    self.v18_manager = selected_managers
    self.v18_class = selected_classes
    self.v18_technician = selected_technicians
    self.v18_competency = selected_competencies
    self.v18_status = selected_statuses
    self.v18_sort_mode = sort_mode

    filtered: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    for effort in efforts:
        identifier = str(effort.get(v18.EFFORT_ID_FIELD) or "")
        linked = linked_by_effort.get(identifier, [])
        if _matches_multi(
            effort,
            linked,
            projects=set(projects),
            managers=set(selected_managers),
            resource_classes=set(selected_classes),
            technicians=set(selected_technicians),
            competencies=set(selected_competencies),
            statuses=set(selected_statuses),
            class_map=class_map,
        ):
            filtered.append((effort, linked))

    filtered.sort(
        key=lambda item: _sort_value(item[0], sort_mode),
        reverse=_sort_descending(sort_mode),
    )
    if group_by_manager:
        filtered.sort(key=lambda item: v18._norm(item[0].get("Chargé de projet")))

    with ui.row().classes("w-full items-center"):
        with ui.column().classes("gap-0"):
            ui.label("Planification moyen terme").classes("text-2xl font-bold")
            ui.label(
                "Enveloppe macro de Liste_Effort avec les segments opérationnels superposés."
            ).classes("muted")
        ui.space()
        ui.button(
            icon="chevron_left",
            on_click=lambda: v13._move_medium_term(self, -8),
        ).props("flat round")
        ui.button(
            "Aujourd'hui",
            on_click=lambda: v13._reset_medium_term(self),
        ).props("outline no-caps")
        ui.button(
            icon="chevron_right",
            on_click=lambda: v13._move_medium_term(self, 8),
        ).props("flat round")
        ui.label(
            f"{window_start.strftime('%d/%m/%Y')} → {window_end.strftime('%d/%m/%Y')}"
        ).classes("font-semibold ml-2")

    def reset_filters() -> None:
        for name in (
            "v18_project",
            "v18_manager",
            "v18_class",
            "v18_technician",
            "v18_competency",
            "v18_status",
        ):
            setattr(self, name, [])
        self.render_content.refresh()

    with ui.card().classes("section-card w-full"):
        ui.label("Les filtres sont multisélection. Une sélection vide signifie « tous ». ").classes(
            "text-xs muted"
        )
        with ui.grid(columns=3).classes("w-full gap-3"):
            ui.select(
                project_options,
                label="Projet",
                value=projects,
                multiple=True,
                with_input=True,
                clearable=True,
                on_change=lambda event: _set_multi_filter(self, "v18_project", event.value),
            ).props("dense use-chips").classes("w-full")
            ui.select(
                managers,
                label="Chargé de projet",
                value=selected_managers,
                multiple=True,
                with_input=True,
                clearable=True,
                on_change=lambda event: _set_multi_filter(self, "v18_manager", event.value),
            ).props("dense use-chips").classes("w-full")
            ui.select(
                statuses,
                label="Statut",
                value=selected_statuses,
                multiple=True,
                clearable=True,
                on_change=lambda event: _set_multi_filter(self, "v18_status", event.value),
            ).props("dense use-chips").classes("w-full")
            ui.select(
                [*v16.RESOURCE_CLASSES, v16.UNCLASSIFIED],
                label="Classe de ressource",
                value=selected_classes,
                multiple=True,
                clearable=True,
                on_change=lambda event: _set_multi_filter(self, "v18_class", event.value),
            ).props("dense use-chips").classes("w-full")
            ui.select(
                technicians,
                label="Technicien",
                value=selected_technicians,
                multiple=True,
                with_input=True,
                clearable=True,
                on_change=lambda event: _set_multi_filter(self, "v18_technician", event.value),
            ).props("dense use-chips").classes("w-full")
            ui.select(
                competencies,
                label="Compétence",
                value=selected_competencies,
                multiple=True,
                with_input=True,
                clearable=True,
                on_change=lambda event: _set_multi_filter(self, "v18_competency", event.value),
            ).props("dense use-chips").classes("w-full")

        with ui.row().classes("w-full items-center gap-3"):
            ui.select(
                SORT_OPTIONS,
                label="Ordre d'affichage",
                value=sort_mode,
                on_change=lambda event: v18._set_filter(self, "v18_sort_mode", event.value),
            ).props("dense").classes("min-w-[260px]")
            ui.checkbox(
                "Regrouper par chargé de projet",
                value=group_by_manager,
                on_change=lambda event: v18._set_filter(
                    self, "v18_group_manager", event.value
                ),
            ).props("dense")
            ui.space()
            ui.button("Réinitialiser les filtres", icon="filter_alt_off", on_click=reset_filters).props(
                "flat dense no-caps"
            )

    _render_capacity_heatmap_multi(self, weeks, class_map, set(selected_classes))

    with ui.row().classes("w-full gap-4 text-xs items-center"):
        ui.label("Légende :").classes("font-semibold")
        ui.badge("Macro Liste_Effort").style("background:#dbeafe;color:#1e3a8a;")
        ui.badge("Segment flexible").style("background:#2563eb;color:white;")
        ui.badge("Segment fixe").style("background:#7c3aed;color:white;")
        ui.badge("Tentatif").style("background:#eab308;color:white;")
        ui.badge("À assigner").style("background:#f97316;color:white;")
        ui.badge("Contour rouge = hors enveloppe").style(
            "background:white;color:#991b1b;border:1px solid #dc2626;"
        )

    if not filtered:
        with ui.card().classes("section-card w-full"):
            ui.label("Aucun effort ne correspond aux filtres et à la fenêtre affichée.").classes(
                "muted"
            )
        return

    with ui.element("div").classes("v18-gantt-scroll w-full"):
        with ui.element("div").classes("v18-gantt-grid"):
            with ui.element("div").classes("v18-sticky v18-header-label"):
                ui.label(f"{len(filtered)} effort(s)").classes("text-xs font-semibold")
            with ui.element("div").classes("v18-week-header"):
                for week in weeks:
                    with ui.element("div").classes("v18-week-cell"):
                        ui.label(week.strftime("%d/%m")).classes("text-[10px] font-semibold")
                        ui.label("S" + week.strftime("%W")).classes("text-[9px] muted")

            last_group: str | None = None
            today_week = v18.week_start()
            today_span = v18._span(
                today_week, today_week + timedelta(days=6), window_start, window_end
            )

            for effort, linked in filtered:
                manager_name = str(
                    effort.get("Chargé de projet") or "Sans chargé de projet"
                ).strip()
                if group_by_manager and manager_name != last_group:
                    with ui.element("div").classes("v18-sticky v18-group-label"):
                        ui.label(manager_name).classes("font-semibold text-sm")
                    ui.element("div").classes("v18-group-fill")
                    last_group = manager_name

                effort_start = _date_from_any(effort.get("Date de début"))
                effort_end = _date_from_any(effort.get("Date de fin")) or effort_start
                total = v13._number(effort.get("Efforts Prévus"))
                detailed = sum(v13._number(segment.get("HeuresPrevues")) for segment in linked)
                delta = total - detailed
                outside_count = 0
                for segment in linked:
                    seg_start, seg_end = v13._segment_dates(segment)
                    if (
                        effort_start
                        and effort_end
                        and seg_start
                        and seg_end
                        and (seg_start < effort_start or seg_end > effort_end)
                    ):
                        outside_count += 1

                with ui.element("div").classes("v18-sticky v18-effort-label").on(
                    "click",
                    lambda _, current=effort: v13._open_effort_macro_dialog(self, current),
                ):
                    ui.label(
                        f"{effort.get('N° projet') or '—'} · {effort.get('Projet') or ''}"
                    ).classes("text-xs font-semibold")
                    meta = [
                        str(effort.get("Compétence") or "").strip(),
                        str(effort.get("Équipe/Technicien attitré") or "Non assigné").strip(),
                        str(effort.get("Status") or "").strip(),
                    ]
                    ui.label(" · ".join(item for item in meta if item)).classes(
                        "text-[10px] muted"
                    )
                    delta_text = (
                        f"reste {delta:.1f} h"
                        if delta >= 0
                        else f"dépassement détaillé {abs(delta):.1f} h"
                    )
                    ui.label(
                        f"{total:.1f} h macro · {detailed:.1f} h segmentées · {delta_text}"
                    ).classes("text-[10px]")
                    if outside_count:
                        ui.label(
                            f"⚠ {outside_count} segment(s) hors enveloppe macro"
                        ).classes("text-[10px] text-red-700")

                row_height = max(58, 36 + len(linked) * 22)
                with ui.element("div").classes("v18-timeline-row").style(
                    f"height:{row_height}px;"
                ):
                    if today_span:
                        left, width = today_span
                        ui.element("div").classes("v18-current-week").style(
                            f"left:{left:.4f}%;width:{width:.4f}%;"
                        )
                    macro_span = v18._span(effort_start, effort_end, window_start, window_end)
                    if macro_span:
                        left, width = macro_span
                        with ui.element("div").classes("v18-macro-bar").style(
                            f"left:{left:.4f}%;width:{width:.4f}%;"
                        ):
                            ui.label(f"{total:g} h").classes("text-[9px] text-blue-900 px-1")

                    for index, segment in enumerate(linked):
                        start, end = v13._segment_dates(segment)
                        segment_span = v18._span(start, end, window_start, window_end)
                        if not segment_span:
                            continue
                        left, width = segment_span
                        tech = str(segment.get("Technicien") or "À assigner").strip()
                        text = f"{tech} · {v13._number(segment.get('HeuresPrevues')):g} h"
                        bar = ui.element("div").classes("v18-segment-bar").style(
                            f"left:{left:.4f}%;width:{width:.4f}%;top:{31 + index * 22}px;"
                            + v18._segment_style(segment, effort_start, effort_end, demands)
                        ).on(
                            "click",
                            lambda _, current=segment: v13._open_segment_dialog(
                                self, segment=current
                            ),
                        )
                        with bar:
                            ui.label(text).classes("text-[9px]")
                        confirmation = v18._confirmation_for_segment(segment, demands)
                        bar.tooltip(
                            f"{segment.get('IDSegment') or ''} · {tech} · "
                            f"{start.strftime('%d/%m/%Y') if start else '—'} → "
                            f"{end.strftime('%d/%m/%Y') if end else '—'} · "
                            f"{v13._number(segment.get('HeuresPrevues')):g} h · "
                            f"{segment.get('TypePlanification') or 'Flexible'} · {confirmation}"
                        )


def _planning_items_for_demand(
    repo: ExcelRepository, number: str
) -> tuple[list[dict[str, Any]], int]:
    segments = [
        row
        for row in v13.segment_records(repo, include_cancelled=True)
        if str(row.get("NoDemande") or "") == number
        and str(row.get("Statut") or "") != "Annulé"
    ]
    segment_ids = {str(row.get("IDSegment") or "") for row in segments}
    allocations = [
        row
        for row in v15_engine.allocation_records(repo)
        if str(row.get("NoDemande") or "") == number
        or str(row.get("IDSegment") or "") in segment_ids
    ]
    return segments, len(allocations)


def _cascade_cancelled_planning(repo: ExcelRepository, number: str) -> tuple[int, int]:
    segments, allocation_count = _planning_items_for_demand(repo, number)
    if not segments and allocation_count <= 0:
        return 0, 0

    with repo.batch_update(f"cancel demand {number}"):
        if segments:
            sheet = repo._book().sheets[v13.SEGMENT_SHEET]
            last_col = int(sheet.used_range.last_cell.column)
            headers = _as_matrix(sheet.range((1, 1), (1, last_col)).value)[0]
            header_map = {
                str(value).strip(): index + 1
                for index, value in enumerate(headers)
                if value not in (None, "")
            }
            status_col = header_map.get("Statut")
            modified_col = header_map.get("DateModification")
            for segment in segments:
                row_number = int(segment.get("_row") or 0)
                if not row_number:
                    continue
                if status_col:
                    sheet.range((row_number, status_col)).value = "Annulé"
                if modified_col:
                    sheet.range((row_number, modified_col)).value = datetime.now()
            repo.save()

        # AllocationsMO is a derived planning table. Rebuilding after cancelling the
        # parent segments removes both automatic and locked/manual allocations that
        # belong to those segments, immediately freeing capacity in the planning.
        v15_engine.rebuild_allocations(repo)
        repo.log_history(
            number,
            "Annulation planification",
            "Annulée",
            "Annulée",
            "Planification associée annulée automatiquement",
            details=(
                f"{len(segments)} segment(s) marqués Annulé; "
                f"{allocation_count} quart(s)/allocation(s) retiré(s) du planning actif."
            ),
        )
    return len(segments), allocation_count


def _install_cancellation_cascade() -> None:
    if getattr(ExcelRepository, "_v18_cancel_cascade_installed", False):
        return

    original_update_demand = ExcelRepository.update_demand

    def update_demand(
        self: ExcelRepository,
        number: str,
        updates: dict[str, Any],
        action: str = "Modification",
        comment: str = "",
    ) -> None:
        cancelling = str(updates.get("Statut") or "").strip() == "Annulée"
        if not cancelling:
            original_update_demand(self, number, updates, action, comment)
            return

        with self.batch_update(f"cancel request {number}"):
            original_update_demand(self, number, updates, action, comment)
            _cascade_cancelled_planning(self, number)

    ExcelRepository.update_demand = update_demand
    ExcelRepository._v18_cancel_cascade_installed = True


def _cancel_request_with_confirmation(
    self: ui_module.PlannerUI, demand: dict[str, Any]
) -> None:
    number = str(demand.get("NoDemande") or "")
    segments, allocation_count = _planning_items_for_demand(self.repo, number)
    self.interaction_lock = True

    with ui.dialog() as dialog, ui.card().classes("w-[650px] max-w-full"):
        ui.label("Annuler la demande").classes("text-xl font-bold text-red-800")
        ui.label(
            f"{number} · {demand.get('NumeroProjet') or '—'} · {demand.get('NomProjet') or ''}"
        ).classes("font-semibold")
        if segments or allocation_count:
            ui.label(
                "La demande est déjà planifiée. L'annulation va libérer la capacité associée."
            ).classes("text-sm")
            ui.label(
                f"{len(segments)} segment(s) seront conservés dans l'historique avec le statut Annulé; "
                f"{allocation_count} quart(s)/allocation(s) seront retirés du planning actif."
            ).classes("text-sm text-amber-800")
        else:
            ui.label("Aucun segment ou quart actif n'est associé à cette demande.").classes(
                "text-sm muted"
            )
        ui.label(
            "Les segments ne sont pas supprimés : ils restent disponibles comme trace de la planification annulée."
        ).classes("text-xs muted")

        def confirm() -> None:
            try:
                self.repo.update_demand(
                    number,
                    {"Statut": "Annulée"},
                    action="Annulation",
                    comment="Demande annulée",
                )
                dialog.close()
                self._after_write("Demande et planification associée annulées")
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        with ui.row().classes("w-full justify-end"):
            ui.button("Retour", on_click=dialog.close).props("flat no-caps")
            ui.button("Confirmer l'annulation", icon="cancel", on_click=confirm).props(
                "unelevated no-caps color=negative"
            )

    dialog.on("hide", lambda _: self._unlock())
    dialog.open()


def install_v18_refinements() -> None:
    if getattr(ui_module.PlannerUI, "_v18_refinements_installed", False):
        return

    _install_cancellation_cascade()

    # The operational calendar was vertically constrained to 100vh - 360px. Make
    # the actual calendar the dominant part of the page and give each day more room.
    ui.add_css(
        """
        @supports selector(.q-scrollarea:has(.schedule-grid)) {
          .q-scrollarea:has(.schedule-grid) {
            height: clamp(620px, calc(100vh - 210px), 920px) !important;
          }
        }
        .schedule-grid {
          grid-template-columns: 190px repeat(7, minmax(165px, 1fr)) !important;
          min-width: 1345px !important;
        }
        """
    )

    previous_render_content = ui_module.PlannerUI._render_content

    def render_content(self: ui_module.PlannerUI) -> None:
        if self.current_page == "medium_term":
            _render_medium_term_refined(self)
            return
        previous_render_content(self)

    ui_module.PlannerUI._render_content = render_content
    ui_module.PlannerUI.render_medium_term = _render_medium_term_refined
    ui_module.PlannerUI.cancel_request = _cancel_request_with_confirmation
    ui_module.PlannerUI._v18_refinements_installed = True
