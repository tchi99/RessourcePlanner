from __future__ import annotations

from contextlib import nullcontext
from datetime import date, timedelta
from typing import Any

from nicegui import ui

from . import v13, v15_refinements, v16, v16_refinements
from . import ui as ui_module
from .bugfixes import schedulable_technicians
from .excel_repository import (
    DEMAND_HEADERS,
    ExcelRepository,
    MASTER_SHEETS,
    _as_matrix,
    _best_header_row,
    _date_from_any,
)
from .services import week_start


EFFORT_ID_FIELD = "IDEffort"
SOURCE_EFFORT_ID_FIELD = "SourceEffortID"
EFFORT_SHEET = "Liste_Effort"
GANTT_WEEKS = 16

ALL_PROJECTS = "Tous les projets"
ALL_PROJECT_MANAGERS = "Tous les chargés de projet"
ALL_CLASSES = "Toutes les classes"
ALL_TECHNICIANS = "Tous les techniciens"
ALL_COMPETENCIES = "Toutes les compétences"
ALL_STATUSES = "Tous les statuts"


def _batch(repo: ExcelRepository, label: str):
    factory = getattr(repo, "batch_update", None)
    return factory(label) if callable(factory) else nullcontext(repo)


def _column_matrix(value: Any) -> list[list[Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        return [[value]]
    if not value:
        return []
    if isinstance(value[0], list):
        return value
    return [[item] for item in value]


def _norm(value: Any) -> str:
    return v16._normalized_text(value)


def _effort_table_and_header(repo: ExcelRepository) -> tuple[Any | None, int, int, list[Any]]:
    sheet = repo._book().sheets[EFFORT_SHEET]

    try:
        for table in sheet.tables:
            first_row = int(table.range.row)
            first_col = int(table.range.column)
            last_col = int(table.range.last_cell.column)
            headers = _as_matrix(
                sheet.range((first_row, first_col), (first_row, last_col)).value
            )
            row = headers[0] if headers else []
            if any(str(value or "").strip() == "N° projet" for value in row):
                return table, first_row, first_col, row
    except Exception:
        pass

    used = sheet.used_range
    matrix = _as_matrix(used.value)
    header_relative = _best_header_row(matrix)
    header_row = int(used.row) + header_relative - 1
    first_col = int(used.column)
    last_col = int(used.last_cell.column)
    headers = _as_matrix(
        sheet.range((header_row, first_col), (header_row, last_col)).value
    )
    return None, header_row, first_col, headers[0] if headers else []


def _ensure_effort_id_column(repo: ExcelRepository) -> tuple[int, int]:
    sheet = repo._book().sheets[EFFORT_SHEET]
    table, header_row, first_col, headers = _effort_table_and_header(repo)

    for offset, raw in enumerate(headers):
        if str(raw or "").strip() == EFFORT_ID_FIELD:
            return header_row, first_col + offset

    last_header_offset = max(
        (index for index, value in enumerate(headers) if value not in (None, "")),
        default=-1,
    )
    target_col = first_col + last_header_offset + 1
    sheet.range((header_row, target_col)).value = EFFORT_ID_FIELD

    if table is not None:
        try:
            last_row = max(int(table.range.last_cell.row), header_row + 1)
            table.resize(
                sheet.range(
                    (int(table.range.row), int(table.range.column)),
                    (last_row, target_col),
                )
            )
        except Exception:
            pass

    try:
        source = sheet.range((header_row, max(target_col - 1, first_col)))
        target = sheet.range((header_row, target_col))
        target.color = source.color
        target.font.bold = source.font.bold
        target.font.color = source.font.color
    except Exception:
        pass

    return header_row, target_col


def _next_effort_ids(existing: list[str], count: int) -> list[str]:
    year = date.today().year
    prefix = f"EFF-{year}-"
    maximum = 0
    for value in existing:
        text = str(value or "").strip()
        if not text.startswith(prefix):
            continue
        try:
            maximum = max(maximum, int(text[len(prefix) :]))
        except ValueError:
            pass
    return [f"{prefix}{maximum + index:05d}" for index in range(1, count + 1)]


def _ensure_effort_ids(repo: ExcelRepository) -> dict[int, str]:
    header_row, id_col = _ensure_effort_id_column(repo)
    rows = repo._sheet_as_records(EFFORT_SHEET, "N° projet")
    rows = [row for row in rows if row.get("N° projet") not in (None, "")]
    if not rows:
        return {}

    existing = [
        str(row.get(EFFORT_ID_FIELD) or "").strip()
        for row in rows
        if str(row.get(EFFORT_ID_FIELD) or "").strip()
    ]
    missing = [row for row in rows if not str(row.get(EFFORT_ID_FIELD) or "").strip()]
    generated = iter(_next_effort_ids(existing, len(missing)))
    generated_by_row: dict[int, str] = {}
    for row in missing:
        generated_by_row[int(row["_row"])] = next(generated)

    if generated_by_row:
        sheet = repo._book().sheets[EFFORT_SHEET]
        last_row = max(int(row["_row"]) for row in rows)
        values = _column_matrix(
            sheet.range((header_row + 1, id_col), (last_row, id_col)).value
        )
        while len(values) < last_row - header_row:
            values.append([None])
        for excel_row, identifier in generated_by_row.items():
            values[excel_row - header_row - 1] = [identifier]
        sheet.range((header_row + 1, id_col), (last_row, id_col)).value = values
        repo.save()
        rows = repo._sheet_as_records(EFFORT_SHEET, "N° projet")

    return {
        int(row["_row"]): str(row.get(EFFORT_ID_FIELD) or "").strip()
        for row in rows
        if row.get("_row") and str(row.get(EFFORT_ID_FIELD) or "").strip()
    }


def _ensure_app_table_headers(
    repo: ExcelRepository, sheet_name: str, headers: list[str], table_name: str
) -> None:
    repo._ensure_sheet_table(sheet_name, headers, table_name)
    try:
        sheet = repo._book().sheets[sheet_name]
        table = sheet.tables[table_name]
        last_row = max(int(table.range.last_cell.row), 2)
        table.resize(sheet.range((1, 1), (last_row, len(headers))))
    except Exception:
        pass


def _migrate_source_ids(
    repo: ExcelRepository,
    sheet_name: str,
    headers: list[str],
    key_field: str,
    row_to_id: dict[int, str],
) -> None:
    if SOURCE_EFFORT_ID_FIELD not in headers:
        return
    records = repo._sheet_as_records(sheet_name, key_field)
    if not records:
        return

    target_col = headers.index(SOURCE_EFFORT_ID_FIELD) + 1
    last_row = max(int(row["_row"]) for row in records)
    sheet = repo._book().sheets[sheet_name]
    values = _column_matrix(sheet.range((2, target_col), (last_row, target_col)).value)
    while len(values) < last_row - 1:
        values.append([None])

    changed = False
    for row in records:
        if str(row.get(SOURCE_EFFORT_ID_FIELD) or "").strip():
            continue
        try:
            source_row = int(float(row.get(v13.SOURCE_EFFORT_FIELD)))
        except (TypeError, ValueError):
            continue
        identifier = row_to_id.get(source_row)
        if not identifier:
            continue
        values[int(row["_row"]) - 2] = [identifier]
        changed = True

    if changed:
        sheet.range((2, target_col), (last_row, target_col)).value = values
        repo.save()


def ensure_v18_schema(repo: ExcelRepository) -> None:
    marker = (str(repo.path or ""), tuple(DEMAND_HEADERS), tuple(v13.SEGMENT_HEADERS))
    if getattr(repo, "_v18_schema_ready", None) == marker:
        return

    with _batch(repo, "V1.8 stable effort links"):
        _ensure_app_table_headers(repo, "DemandesMO", DEMAND_HEADERS, "DemandesMOTable")
        _ensure_app_table_headers(repo, v13.SEGMENT_SHEET, v13.SEGMENT_HEADERS, v13.SEGMENT_TABLE)
        row_to_id = _ensure_effort_ids(repo)
        _migrate_source_ids(repo, "DemandesMO", DEMAND_HEADERS, "NoDemande", row_to_id)
        _migrate_source_ids(
            repo, v13.SEGMENT_SHEET, v13.SEGMENT_HEADERS, "IDSegment", row_to_id
        )

    repo._v18_schema_ready = marker


def _effort_maps(repo: ExcelRepository) -> tuple[dict[int, str], dict[str, dict[str, Any]]]:
    ensure_v18_schema(repo)
    rows = repo.efforts(include_closed=True)
    row_to_id: dict[int, str] = {}
    by_id: dict[str, dict[str, Any]] = {}
    for effort in rows:
        identifier = str(effort.get(EFFORT_ID_FIELD) or "").strip()
        row = int(effort.get("_row") or 0)
        if identifier:
            by_id[identifier] = effort
            if row:
                row_to_id[row] = identifier
    return row_to_id, by_id


def _source_id_for_payload(repo: ExcelRepository, payload: dict[str, Any]) -> str | None:
    existing = str(payload.get(SOURCE_EFFORT_ID_FIELD) or "").strip()
    if existing:
        return existing
    try:
        source_row = int(float(payload.get(v13.SOURCE_EFFORT_FIELD)))
    except (TypeError, ValueError):
        source_row = 0
    if source_row:
        row_to_id, _ = _effort_maps(repo)
        identifier = row_to_id.get(source_row)
        if identifier:
            return identifier

    demand_number = str(payload.get("NoDemande") or "").strip()
    if demand_number:
        demand = next(
            (
                row
                for row in repo.demands()
                if str(row.get("NoDemande") or "").strip() == demand_number
            ),
            None,
        )
        if demand:
            identifier = str(demand.get(SOURCE_EFFORT_ID_FIELD) or "").strip()
            if identifier:
                return identifier
    return None


def _linked_segments(
    repo: ExcelRepository,
    effort: dict[str, Any],
    segments: list[dict[str, Any]] | None = None,
    demands: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    identifier = str(effort.get(EFFORT_ID_FIELD) or "").strip()
    row_number = int(effort.get("_row") or 0)
    segments = segments if segments is not None else v13.segment_records(repo, include_cancelled=False)
    demands = demands if demands is not None else {
        str(row.get("NoDemande") or ""): row for row in repo.demands()
    }

    result: list[dict[str, Any]] = []
    for segment in segments:
        segment_id = str(segment.get(SOURCE_EFFORT_ID_FIELD) or "").strip()
        if identifier and segment_id == identifier:
            result.append(segment)
            continue
        demand = demands.get(str(segment.get("NoDemande") or ""), {})
        demand_id = str(demand.get(SOURCE_EFFORT_ID_FIELD) or "").strip()
        if identifier and demand_id == identifier:
            result.append(segment)
            continue
        if row_number:
            try:
                if int(float(segment.get(v13.SOURCE_EFFORT_FIELD))) == row_number:
                    result.append(segment)
            except (TypeError, ValueError):
                pass
    return result


def _overlap(start: date | None, end: date | None, window_start: date, window_end: date) -> bool:
    end = end or start
    return bool(start and end and start <= window_end and end >= window_start)


def _span(
    start: date | None, end: date | None, window_start: date, window_end: date
) -> tuple[float, float] | None:
    end = end or start
    if not start or not end or not _overlap(start, end, window_start, window_end):
        return None
    clipped_start = max(start, window_start)
    clipped_end = min(end, window_end)
    total_days = (window_end - window_start).days + 1
    left = (clipped_start - window_start).days / total_days * 100
    width = ((clipped_end - clipped_start).days + 1) / total_days * 100
    return left, max(width, 0.4)


def _set_filter(self: ui_module.PlannerUI, name: str, value: Any) -> None:
    setattr(self, name, value)
    self.render_content.refresh()


def _filter_value(self: ui_module.PlannerUI, name: str, default: Any) -> Any:
    return getattr(self, name, default)


def _effort_matches(
    effort: dict[str, Any],
    linked: list[dict[str, Any]],
    *,
    project: str,
    manager: str,
    resource_class: str,
    technician: str,
    competency: str,
    status: str,
    class_map: dict[str, str],
) -> bool:
    if project != ALL_PROJECTS and str(effort.get("N° projet") or "") != project:
        return False
    if manager != ALL_PROJECT_MANAGERS and str(effort.get("Chargé de projet") or "") != manager:
        return False
    if status != ALL_STATUSES and str(effort.get("Status") or "") != status:
        return False

    effort_tech = str(effort.get("Équipe/Technicien attitré") or "").strip()
    linked_techs = {
        str(segment.get("Technicien") or "").strip()
        for segment in linked
        if str(segment.get("Technicien") or "").strip()
    }
    all_techs = linked_techs | ({effort_tech} if effort_tech else set())
    if technician != ALL_TECHNICIANS and technician not in all_techs:
        return False
    if resource_class != ALL_CLASSES:
        if not any(class_map.get(name, v16.UNCLASSIFIED) == resource_class for name in all_techs):
            return False

    if competency != ALL_COMPETENCIES:
        wanted = _norm(competency)
        candidates = {_norm(effort.get("Compétence"))}
        candidates.update(_norm(segment.get("CompetenceRequise")) for segment in linked)
        if wanted not in candidates:
            return False

    return True


def _confirmation_for_segment(
    segment: dict[str, Any], demands: dict[str, dict[str, Any]]
) -> str:
    demand = demands.get(str(segment.get("NoDemande") or ""), {})
    return v15_refinements.demand_confirmation(demand)


def _segment_style(
    segment: dict[str, Any],
    effort_start: date | None,
    effort_end: date | None,
    demands: dict[str, dict[str, Any]],
) -> str:
    technician = str(segment.get("Technicien") or "").strip()
    plan_type = str(segment.get("TypePlanification") or "Flexible")
    confirmation = _confirmation_for_segment(segment, demands)
    start, end = v13._segment_dates(segment)
    outside = bool(
        effort_start
        and effort_end
        and start
        and end
        and (start < effort_start or end > effort_end)
    )

    background = "#7c3aed" if plan_type == "Fixe" else "#2563eb"
    if not technician:
        background = "#f97316"
    if confirmation == "Tentative":
        background = "#eab308"

    border = "2px solid #dc2626" if outside else "1px solid rgba(255,255,255,.7)"
    border_style = "dashed" if confirmation == "Tentative" else "solid"
    return (
        f"background:{background};border:{border};border-style:{border_style};"
        "color:white;border-radius:5px;overflow:hidden;white-space:nowrap;"
        "padding:1px 5px;cursor:pointer;box-shadow:0 1px 2px rgba(0,0,0,.12);"
    )


def _render_capacity_heatmap(
    self: ui_module.PlannerUI,
    weeks: list[date],
    class_map: dict[str, str],
    selected_class: str,
) -> None:
    techs = [row["name"] for row in schedulable_technicians(self.repo)]
    allocations = v16._actual_allocations(self.repo)
    classes = list(v16.RESOURCE_CLASSES)
    if any(class_map.get(name, v16.UNCLASSIFIED) == v16.UNCLASSIFIED for name in techs):
        classes.append(v16.UNCLASSIFIED)
    if selected_class != ALL_CLASSES:
        classes = [item for item in classes if item == selected_class]

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


def _render_medium_term_v18(self: ui_module.PlannerUI) -> None:
    ensure_v18_schema(self.repo)
    if not hasattr(self, "medium_term_start"):
        self.medium_term_start = week_start() - timedelta(weeks=2)

    window_start: date = self.medium_term_start
    weeks = [window_start + timedelta(weeks=index) for index in range(GANTT_WEEKS)]
    window_end = weeks[-1] + timedelta(days=6)

    efforts = [
        effort
        for effort in self.repo.efforts(include_closed=False)
        if _overlap(
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
        identifier = str(effort.get(EFFORT_ID_FIELD) or "")
        linked_by_effort[identifier] = _linked_segments(self.repo, effort, segments, demands)

    project_options: dict[str, str] = {ALL_PROJECTS: ALL_PROJECTS}
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
        key=_norm,
    )
    technicians = sorted(
        {
            str(row.get("name") or "").strip()
            for row in schedulable_technicians(self.repo)
            if str(row.get("name") or "").strip()
        },
        key=_norm,
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
        key=_norm,
    )
    statuses = sorted(
        {
            str(effort.get("Status") or "").strip()
            for effort in efforts
            if str(effort.get("Status") or "").strip()
        },
        key=_norm,
    )

    project = _filter_value(self, "v18_project", ALL_PROJECTS)
    manager = _filter_value(self, "v18_manager", ALL_PROJECT_MANAGERS)
    resource_class = _filter_value(self, "v18_class", ALL_CLASSES)
    technician = _filter_value(self, "v18_technician", ALL_TECHNICIANS)
    competency = _filter_value(self, "v18_competency", ALL_COMPETENCIES)
    status = _filter_value(self, "v18_status", ALL_STATUSES)
    group_by_manager = bool(_filter_value(self, "v18_group_manager", True))

    valid_values = {
        "v18_project": set(project_options),
        "v18_manager": {ALL_PROJECT_MANAGERS, *managers},
        "v18_class": {ALL_CLASSES, *v16.RESOURCE_CLASSES, v16.UNCLASSIFIED},
        "v18_technician": {ALL_TECHNICIANS, *technicians},
        "v18_competency": {ALL_COMPETENCIES, *competencies},
        "v18_status": {ALL_STATUSES, *statuses},
    }
    defaults = {
        "v18_project": ALL_PROJECTS,
        "v18_manager": ALL_PROJECT_MANAGERS,
        "v18_class": ALL_CLASSES,
        "v18_technician": ALL_TECHNICIANS,
        "v18_competency": ALL_COMPETENCIES,
        "v18_status": ALL_STATUSES,
    }
    for attr, choices in valid_values.items():
        current = getattr(self, attr, defaults[attr])
        if current not in choices:
            setattr(self, attr, defaults[attr])

    project = getattr(self, "v18_project", ALL_PROJECTS)
    manager = getattr(self, "v18_manager", ALL_PROJECT_MANAGERS)
    resource_class = getattr(self, "v18_class", ALL_CLASSES)
    technician = getattr(self, "v18_technician", ALL_TECHNICIANS)
    competency = getattr(self, "v18_competency", ALL_COMPETENCIES)
    status = getattr(self, "v18_status", ALL_STATUSES)

    filtered: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    for effort in efforts:
        identifier = str(effort.get(EFFORT_ID_FIELD) or "")
        linked = linked_by_effort.get(identifier, [])
        if _effort_matches(
            effort,
            linked,
            project=project,
            manager=manager,
            resource_class=resource_class,
            technician=technician,
            competency=competency,
            status=status,
            class_map=class_map,
        ):
            filtered.append((effort, linked))

    filtered.sort(
        key=lambda item: (
            _norm(item[0].get("Chargé de projet")) if group_by_manager else "",
            _date_from_any(item[0].get("Date de début")) or date.max,
            _norm(item[0].get("N° projet")),
        )
    )

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

    with ui.card().classes("section-card w-full"):
        with ui.grid(columns=3).classes("w-full gap-3"):
            ui.select(
                project_options,
                label="Projet",
                value=project,
                on_change=lambda event: _set_filter(self, "v18_project", event.value),
            ).props("dense").classes("w-full")
            ui.select(
                [ALL_PROJECT_MANAGERS, *managers],
                label="Chargé de projet",
                value=manager,
                on_change=lambda event: _set_filter(self, "v18_manager", event.value),
            ).props("dense").classes("w-full")
            ui.select(
                [ALL_STATUSES, *statuses],
                label="Statut",
                value=status,
                on_change=lambda event: _set_filter(self, "v18_status", event.value),
            ).props("dense").classes("w-full")
            ui.select(
                [ALL_CLASSES, *v16.RESOURCE_CLASSES, v16.UNCLASSIFIED],
                label="Classe de ressource",
                value=resource_class,
                on_change=lambda event: _set_filter(self, "v18_class", event.value),
            ).props("dense").classes("w-full")
            ui.select(
                [ALL_TECHNICIANS, *technicians],
                label="Technicien",
                value=technician,
                on_change=lambda event: _set_filter(self, "v18_technician", event.value),
                with_input=True,
            ).props("dense").classes("w-full")
            ui.select(
                [ALL_COMPETENCIES, *competencies],
                label="Compétence",
                value=competency,
                on_change=lambda event: _set_filter(self, "v18_competency", event.value),
                with_input=True,
            ).props("dense").classes("w-full")

        ui.checkbox(
            "Regrouper par chargé de projet",
            value=group_by_manager,
            on_change=lambda event: _set_filter(self, "v18_group_manager", event.value),
        ).props("dense")

    _render_capacity_heatmap(self, weeks, class_map, resource_class)

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
            today_week = week_start()
            today_span = _span(
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
                    macro_span = _span(effort_start, effort_end, window_start, window_end)
                    if macro_span:
                        left, width = macro_span
                        with ui.element("div").classes("v18-macro-bar").style(
                            f"left:{left:.4f}%;width:{width:.4f}%;"
                        ):
                            ui.label(f"{total:g} h").classes("text-[9px] text-blue-900 px-1")

                    for index, segment in enumerate(linked):
                        start, end = v13._segment_dates(segment)
                        segment_span = _span(start, end, window_start, window_end)
                        if not segment_span:
                            continue
                        left, width = segment_span
                        tech = str(segment.get("Technicien") or "À assigner").strip()
                        text = f"{tech} · {v13._number(segment.get('HeuresPrevues')):g} h"
                        bar = ui.element("div").classes("v18-segment-bar").style(
                            f"left:{left:.4f}%;width:{width:.4f}%;top:{31 + index * 22}px;"
                            + _segment_style(segment, effort_start, effort_end, demands)
                        ).on(
                            "click",
                            lambda _, current=segment: v13._open_segment_dialog(
                                self, segment=current
                            ),
                        )
                        with bar:
                            ui.label(text).classes("text-[9px]")
                        confirmation = _confirmation_for_segment(segment, demands)
                        bar.tooltip(
                            f"{segment.get('IDSegment') or ''} · {tech} · "
                            f"{start.strftime('%d/%m/%Y') if start else '—'} → "
                            f"{end.strftime('%d/%m/%Y') if end else '—'} · "
                            f"{v13._number(segment.get('HeuresPrevues')):g} h · "
                            f"{segment.get('TypePlanification') or 'Flexible'} · {confirmation}"
                        )


def _install_stable_link_wrappers() -> None:
    if getattr(ExcelRepository, "_v18_stable_links_installed", False):
        return

    original_ensure = ExcelRepository.ensure_app_sheets
    original_create_demand = ExcelRepository.create_demand
    original_update_demand = ExcelRepository.update_demand
    original_add_segment = v13.add_segment
    original_update_segment = v13.update_segment

    def ensure_app_sheets(self: ExcelRepository) -> None:
        original_ensure(self)
        ensure_v18_schema(self)

    def create_demand(
        self: ExcelRepository, data: dict[str, Any], submit: bool = False
    ) -> str:
        ensure_v18_schema(self)
        payload = dict(data)
        source_id = _source_id_for_payload(self, payload)
        if source_id:
            payload[SOURCE_EFFORT_ID_FIELD] = source_id
        return original_create_demand(self, payload, submit)

    def update_demand(
        self: ExcelRepository,
        number: str,
        updates: dict[str, Any],
        action: str = "Modification",
        comment: str = "",
    ) -> None:
        ensure_v18_schema(self)
        payload = dict(updates)
        source_id = _source_id_for_payload(self, payload)
        if source_id:
            payload[SOURCE_EFFORT_ID_FIELD] = source_id
        original_update_demand(self, number, payload, action, comment)

    def add_segment(repo: ExcelRepository, values: dict[str, Any]) -> str:
        ensure_v18_schema(repo)
        payload = dict(values)
        source_id = _source_id_for_payload(repo, payload)
        if source_id:
            payload[SOURCE_EFFORT_ID_FIELD] = source_id
        return original_add_segment(repo, payload)

    def update_segment(
        repo: ExcelRepository, ident: str, updates: dict[str, Any]
    ) -> None:
        ensure_v18_schema(repo)
        payload = dict(updates)
        source_id = _source_id_for_payload(repo, payload)
        if source_id:
            payload[SOURCE_EFFORT_ID_FIELD] = source_id
        original_update_segment(repo, ident, payload)

    ExcelRepository.ensure_app_sheets = ensure_app_sheets
    ExcelRepository.create_demand = create_demand
    ExcelRepository.update_demand = update_demand
    v13.add_segment = add_segment
    v13.update_segment = update_segment
    ExcelRepository._v18_stable_links_installed = True


def install_v18_features() -> None:
    if getattr(ui_module.PlannerUI, "_v18_features_installed", False):
        return

    if SOURCE_EFFORT_ID_FIELD not in DEMAND_HEADERS:
        DEMAND_HEADERS.append(SOURCE_EFFORT_ID_FIELD)
    if SOURCE_EFFORT_ID_FIELD not in v13.SEGMENT_HEADERS:
        v13.SEGMENT_HEADERS.append(SOURCE_EFFORT_ID_FIELD)
    MASTER_SHEETS.add(EFFORT_SHEET)

    _install_stable_link_wrappers()

    ui.add_css(
        """
        .v18-gantt-scroll { overflow-x: auto; border: 1px solid #e5e7eb; border-radius: 10px; }
        .v18-gantt-grid { display:grid; grid-template-columns:340px 1280px; min-width:1620px; background:white; }
        .v18-sticky { position:sticky; left:0; z-index:4; background:white; }
        .v18-header-label { padding:8px 10px; border-bottom:1px solid #d1d5db; }
        .v18-week-header { display:grid; grid-template-columns:repeat(16,1fr); border-bottom:1px solid #d1d5db; }
        .v18-week-cell { padding:5px 2px; text-align:center; border-left:1px solid #e5e7eb; min-height:38px; }
        .v18-group-label { padding:7px 10px; background:#f3f4f6; border-top:1px solid #d1d5db; border-bottom:1px solid #d1d5db; }
        .v18-group-fill { background:#f3f4f6; border-top:1px solid #d1d5db; border-bottom:1px solid #d1d5db; }
        .v18-effort-label { padding:7px 10px; border-bottom:1px solid #e5e7eb; cursor:pointer; min-height:58px; }
        .v18-effort-label:hover { background:#f8fafc; }
        .v18-timeline-row { position:relative; border-bottom:1px solid #e5e7eb;
            background-image:linear-gradient(to right,#e5e7eb 1px,transparent 1px);
            background-size:6.25% 100%; overflow:hidden; }
        .v18-current-week { position:absolute; top:0; bottom:0; background:rgba(59,130,246,.06); z-index:0; }
        .v18-macro-bar { position:absolute; top:7px; height:18px; background:#dbeafe; border:1px solid #93c5fd;
            border-radius:5px; overflow:hidden; z-index:1; }
        .v18-segment-bar { position:absolute; height:18px; z-index:2; }
        .v18-capacity-scroll { overflow-x:auto; width:100%; }
        .v18-capacity-grid { display:grid; grid-template-columns:180px repeat(16,72px); min-width:1332px; align-items:center; gap:2px; }
        .v18-capacity-label { padding:4px 6px; background:white; z-index:3; }
        """
    )

    original_page_sheets = ui_module.PlannerUI._page_sheets

    def page_sheets(self: ui_module.PlannerUI) -> list[str]:
        if self.current_page == "medium_term":
            return [
                EFFORT_SHEET,
                "DemandesMO",
                v13.SEGMENT_SHEET,
                "AllocationsMO",
                "Disponibilites",
                v16_refinements.RESOURCE_PROFILE_SHEET,
            ]
        return original_page_sheets(self)

    ui_module.PlannerUI._page_sheets = page_sheets
    ui_module.PlannerUI.render_medium_term = _render_medium_term_v18

    previous_render_content = ui_module.PlannerUI._render_content

    def render_content(self: ui_module.PlannerUI) -> None:
        if self.current_page == "medium_term":
            _render_medium_term_v18(self)
            return
        previous_render_content(self)

    ui_module.PlannerUI._render_content = render_content
    ui_module.PlannerUI._v18_features_installed = True
