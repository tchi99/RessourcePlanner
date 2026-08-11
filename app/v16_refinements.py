from __future__ import annotations

from typing import Any

from nicegui import ui

from . import features
from . import ui as ui_module
from . import v13, v15, v15_engine, v15_refinements, v16
from .bugfixes import schedulable_technicians
from .excel_repository import ExcelRepository, MASTER_SHEETS, _as_matrix


RESOURCE_PROFILE_SHEET = "RessourcesMO"
RESOURCE_PROFILE_TABLE = "RessourcesMOTable"
RESOURCE_PROFILE_HEADERS = [
    "Technicien",
    "Classe",
    "Competences",
    "Note",
]


def _split_competencies(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    normalized = text.replace("\n", ";").replace(",", ";")
    result: list[str] = []
    for item in normalized.split(";"):
        skill = item.strip()
        if skill and skill not in result:
            result.append(skill)
    return result


def _join_competencies(values: Any) -> str:
    if values in (None, ""):
        return ""
    if isinstance(values, str):
        return "; ".join(_split_competencies(values))
    result: list[str] = []
    for item in values:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return "; ".join(result)


def _profile_records(repo: ExcelRepository) -> list[dict[str, Any]]:
    with repo._lock:
        sheet = repo._book().sheets[RESOURCE_PROFILE_SHEET]
        matrix = _as_matrix(sheet.used_range.value)
        if not matrix:
            return []
        headers = [str(value or "").strip() for value in matrix[0]]
        result: list[dict[str, Any]] = []
        for excel_row, row in enumerate(matrix[1:], start=2):
            technician = str(row[0] if row else "" or "").strip()
            if not technician:
                continue
            item: dict[str, Any] = {"_row": excel_row}
            for index, header in enumerate(headers):
                if not header:
                    continue
                item[header] = row[index] if index < len(row) else None
            result.append(item)
        return result


def ensure_resource_profiles(repo: ExcelRepository) -> None:
    repo._ensure_sheet_table(
        RESOURCE_PROFILE_SHEET,
        RESOURCE_PROFILE_HEADERS,
        RESOURCE_PROFILE_TABLE,
    )
    MASTER_SHEETS.add(RESOURCE_PROFILE_SHEET)

    existing = {
        str(row.get("Technicien") or "").strip()
        for row in _profile_records(repo)
        if str(row.get("Technicien") or "").strip()
    }
    for technician in repo.technicians():
        name = str(technician.get("name") or "").strip()
        if not name or name in existing:
            continue
        repo._append_dict_row(
            RESOURCE_PROFILE_SHEET,
            RESOURCE_PROFILE_HEADERS,
            {
                "Technicien": name,
                "Classe": None,
                "Competences": None,
                "Note": None,
            },
            RESOURCE_PROFILE_TABLE,
        )
        existing.add(name)
    repo.save()


def resource_profile_map(repo: ExcelRepository) -> dict[str, dict[str, Any]]:
    ensure_resource_profiles(repo)
    result: dict[str, dict[str, Any]] = {}
    for row in _profile_records(repo):
        name = str(row.get("Technicien") or "").strip()
        if not name:
            continue
        resource_class = v16._normalize_resource_class(row.get("Classe")) or v16.UNCLASSIFIED
        result[name] = {
            "class": resource_class,
            "competencies": _split_competencies(row.get("Competences")),
            "note": str(row.get("Note") or "").strip(),
            "row": row.get("_row"),
        }
    return result


def resource_class_map(repo: ExcelRepository) -> dict[str, str]:
    profiles = resource_profile_map(repo)
    return {
        str(tech.get("name") or "").strip(): profiles.get(
            str(tech.get("name") or "").strip(), {}
        ).get("class", v16.UNCLASSIFIED)
        for tech in schedulable_technicians(repo)
    }


def resource_competence_map(repo: ExcelRepository) -> dict[str, set[str]]:
    profiles = resource_profile_map(repo)
    return {
        name: {v16._normalized_text(skill) for skill in profile.get("competencies", []) if skill}
        for name, profile in profiles.items()
    }


def update_resource_profile(
    repo: ExcelRepository,
    technician: str,
    resource_class: str | None,
    competencies: Any,
    note: str = "",
) -> None:
    ensure_resource_profiles(repo)
    name = str(technician or "").strip()
    if not name:
        raise ValueError("Le technicien est requis.")

    chosen_class = v16._normalize_resource_class(resource_class)
    if resource_class and not chosen_class:
        raise ValueError("La classe sélectionnée n'est pas reconnue.")

    rows = _profile_records(repo)
    target = next((row for row in rows if str(row.get("Technicien") or "").strip() == name), None)
    if target is None:
        repo._append_dict_row(
            RESOURCE_PROFILE_SHEET,
            RESOURCE_PROFILE_HEADERS,
            {
                "Technicien": name,
                "Classe": chosen_class,
                "Competences": _join_competencies(competencies),
                "Note": note,
            },
            RESOURCE_PROFILE_TABLE,
        )
        return

    excel_row = int(target["_row"])
    with repo._lock:
        sheet = repo._book().sheets[RESOURCE_PROFILE_SHEET]
        sheet.range((excel_row, 1), (excel_row, len(RESOURCE_PROFILE_HEADERS))).value = [[
            name,
            chosen_class,
            _join_competencies(competencies),
            str(note or "").strip() or None,
        ]]
        repo.save()


def recommend_resources(repo: ExcelRepository, segment: dict[str, Any]) -> list[dict[str, Any]]:
    start, end = v13._segment_dates(segment)
    if not start or not end:
        return []

    required = v13._number(segment.get("HeuresPrevues"))
    required_class = v16._required_class(repo, segment)
    required_competence = str(segment.get("CompetenceRequise") or "").strip()
    required_competence_key = v16._normalized_text(required_competence)
    class_map = resource_class_map(repo)
    competence_map = resource_competence_map(repo)
    allocations = v16._actual_allocations(repo)
    demands = v16._demand_lookup(repo)
    segment_id = str(segment.get("IDSegment") or "")
    rows: list[dict[str, Any]] = []

    for tech in schedulable_technicians(repo):
        name = str(tech.get("name") or "").strip()
        stats = v16._resource_window_stats(
            repo,
            name,
            start,
            end,
            exclude_segment_id=segment_id,
            allocations=allocations,
            demands=demands,
        )
        tech_class = class_map.get(name, v16.UNCLASSIFIED)
        skills = competence_map.get(name, set())
        class_match = not required_class or tech_class == required_class
        skill_match = not required_competence_key or required_competence_key in skills
        enough_prudent = stats["prudent_free"] + 0.01 >= required
        enough_confirmed = stats["free_after_confirmed"] + 0.01 >= required
        overtime_needed = max(required - stats["prudent_free"], 0.0)

        score = 0.0
        if skill_match:
            score += 20000
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
                "skill_match": skill_match,
                "required_class": required_class,
                "required_competence": required_competence,
                "required": required,
                "score": score,
                "enough_prudent": enough_prudent,
                "enough_confirmed": enough_confirmed,
                "overtime_needed": round(overtime_needed, 2),
                "skills": sorted(skills),
                **stats,
            }
        )

    rows.sort(
        key=lambda row: (
            -int(bool(row["skill_match"])),
            -int(bool(row["class_match"])),
            -int(bool(row["enough_prudent"])),
            -row["score"],
            -row["prudent_free"],
            row["name"],
        )
    )
    return rows


def _open_recommendation_dialog(
    self: ui_module.PlannerUI,
    segment: dict[str, Any],
) -> None:
    self.interaction_lock = True
    recommendations = recommend_resources(self.repo, segment)
    competence = str(segment.get("CompetenceRequise") or "Compétence non précisée")
    required_class = v16._required_class(self.repo, segment)
    start, end = v13._segment_dates(segment)

    with ui.dialog() as dialog, ui.card().classes("w-[940px] max-w-full"):
        ui.label("Trouver une ressource").classes("text-xl font-bold")
        ui.label(
            f"{segment.get('NumeroProjet') or '—'} · {segment.get('NomProjet') or ''} · "
            f"{v13._number(segment.get('HeuresPrevues')):g} h"
        ).classes("font-semibold")
        ui.label(
            f"Compétence requise : {competence} · Classe : {required_class or 'non déterminée'} · "
            f"Fenêtre : {start.strftime('%d/%m/%Y') if start else '—'} → "
            f"{end.strftime('%d/%m/%Y') if end else '—'}"
        ).classes("text-sm muted")

        if not recommendations:
            ui.label("Aucune ressource planifiable trouvée.").classes("muted")
        else:
            for index, row in enumerate(recommendations):
                recommended = index == 0 and row["skill_match"] and row["class_match"]
                border = "border:2px solid #16a34a;" if recommended else "border:1px solid #e5e7eb;"
                with ui.card().classes("w-full p-3").style(border):
                    with ui.row().classes("w-full items-center"):
                        with ui.column().classes("gap-0 flex-1"):
                            title = f"{row['name']} · {row['class']}"
                            if recommended:
                                title += " · Recommandé"
                            ui.label(title).classes("font-semibold")
                            skill_text = (
                                "Compétence correspondante"
                                if row["skill_match"]
                                else f"Compétence {row['required_competence'] or 'requise'} non attribuée"
                            )
                            ui.label(skill_text).classes(
                                "text-xs text-green-700" if row["skill_match"] else "text-xs text-amber-700"
                            )
                            ui.label(
                                "Classe compatible" if row["class_match"] else f"Classe différente de {row['required_class']}"
                            ).classes(
                                "text-xs text-green-700" if row["class_match"] else "text-xs text-gray-500"
                            )
                            ui.label(
                                f"{row['prudent_free']:.1f} h libres prudentes · "
                                f"{row['free_after_confirmed']:.1f} h après confirmés · "
                                f"{row['tentative']:.1f} h tentatives"
                            ).classes("text-xs")
                            if row["overtime_needed"] > 0:
                                ui.label(
                                    f"Environ {row['overtime_needed']:.1f} h nécessiteraient du hors horaire."
                                ).classes("text-xs text-orange-700")
                        ui.button(
                            "Assigner",
                            icon="person_add",
                            on_click=lambda tech=row["name"]: v16._assign_segment(
                                self, segment, tech, dialog
                            ),
                        ).props("unelevated no-caps color=primary")

        with ui.row().classes("w-full justify-end"):
            ui.button("Fermer", on_click=dialog.close).props("flat no-caps")

    dialog.on("hide", lambda _: self._unlock())
    dialog.open()


def _project_labels(repo: ExcelRepository) -> dict[str, str]:
    labels: dict[str, str] = {v16.ALL_PROJECTS: v16.ALL_PROJECTS}
    try:
        for project in repo.projects(active_only=False):
            number = str(project.get("Numéro de Projet") or "").strip()
            if not number:
                continue
            name = str(
                project.get("Nom de référence")
                or project.get("Description de l'appel d'offre")
                or ""
            ).strip()
            labels[number] = f"{number} — {name}" if name else number
    except Exception:
        pass

    for demand in repo.demands():
        number = str(demand.get("NumeroProjet") or "").strip()
        name = str(demand.get("NomProjet") or "").strip()
        if number and number not in labels:
            labels[number] = f"{number} — {name}" if name else number
    return labels


def _render_planning(self: ui_module.PlannerUI) -> None:
    """Réutilise la vue V1.6 en remplaçant uniquement les libellés du filtre Projet."""
    original_select = v16.ui.select
    labels = _project_labels(self.repo)

    def select_proxy(options: Any, *args: Any, **kwargs: Any) -> Any:
        if kwargs.get("label") == "Projet" and isinstance(options, list) and v16.ALL_PROJECTS in options:
            mapped = {
                value: labels.get(str(value), str(value))
                for value in options
            }
            return original_select(mapped, *args, **kwargs)
        return original_select(options, *args, **kwargs)

    v16.ui.select = select_proxy
    try:
        v16._render_planning_v16(self)
    finally:
        v16.ui.select = original_select


def _render_resources(self: ui_module.PlannerUI) -> None:
    ensure_resource_profiles(self.repo)
    profiles = resource_profile_map(self.repo)
    technicians = self.repo.technicians()
    competencies = list(self.repo.competencies())

    with ui.row().classes("w-full items-center"):
        with ui.column().classes("gap-0"):
            ui.label("Ressources & compétences").classes("text-2xl font-bold")
            ui.label(
                "Attribue explicitement une classe et les compétences utilisables par le moteur de recommandation."
            ).classes("muted")

    with ui.card().classes("section-card w-full"):
        ui.label(
            "Une ressource sans classe reste dans Non classé. Les compétences choisies servent à prioriser les recommandations; elles ne bloquent pas une affectation manuelle."
        ).classes("text-sm muted")

    with ui.grid(columns=2).classes("w-full gap-3"):
        for technician in technicians:
            name = str(technician.get("name") or "").strip()
            if not name:
                continue
            profile = profiles.get(name, {"class": v16.UNCLASSIFIED, "competencies": [], "note": ""})
            current_class = profile.get("class")
            class_value = None if current_class == v16.UNCLASSIFIED else current_class
            with ui.card().classes("section-card w-full p-4"):
                ui.label(name).classes("text-lg font-semibold")
                details = " · ".join(
                    value for value in [str(technician.get("description") or "").strip(), str(technician.get("team") or "").strip()]
                    if value
                )
                if details:
                    ui.label(details).classes("text-xs muted")

                class_select = ui.select(
                    v16.RESOURCE_CLASSES,
                    label="Classe",
                    value=class_value,
                    clearable=True,
                ).classes("w-full")
                competence_select = ui.select(
                    competencies,
                    label="Compétences",
                    value=list(profile.get("competencies") or []),
                    multiple=True,
                    with_input=True,
                    clearable=True,
                ).classes("w-full")
                note_input = ui.input(
                    "Note (optionnel)",
                    value=str(profile.get("note") or ""),
                ).classes("w-full")

                def save_profile(
                    tech_name: str = name,
                    class_control: Any = class_select,
                    skills_control: Any = competence_select,
                    note_control: Any = note_input,
                ) -> None:
                    try:
                        update_resource_profile(
                            self.repo,
                            tech_name,
                            class_control.value,
                            skills_control.value or [],
                            note_control.value or "",
                        )
                        self._after_write(f"Profil de {tech_name} enregistré")
                    except Exception as exc:
                        ui.notify(str(exc), type="negative")

                ui.button("Enregistrer", icon="save", on_click=save_profile).props(
                    "unelevated no-caps color=primary"
                )


def install_v16_refinements() -> None:
    if getattr(ui_module.PlannerUI, "_v16_refinements_installed", False):
        return

    original_ensure = ExcelRepository.ensure_app_sheets

    def ensure_app_sheets(self: ExcelRepository) -> None:
        original_ensure(self)
        ensure_resource_profiles(self)

    ExcelRepository.ensure_app_sheets = ensure_app_sheets

    if not any(item[0] == "resources" for item in ui_module.NAV_ITEMS):
        settings_index = next(
            (index for index, item in enumerate(ui_module.NAV_ITEMS) if item[0] == "settings"),
            len(ui_module.NAV_ITEMS),
        )
        ui_module.NAV_ITEMS.insert(
            settings_index,
            ("resources", "engineering", "Ressources & compétences"),
        )

    previous_render_content = ui_module.PlannerUI._render_content
    previous_page_sheets = ui_module.PlannerUI._page_sheets

    def render_content(self: ui_module.PlannerUI) -> None:
        if self.current_page == "resources":
            _render_resources(self)
            return
        previous_render_content(self)

    def page_sheets(self: ui_module.PlannerUI) -> list[str]:
        if self.current_page == "resources":
            return [RESOURCE_PROFILE_SHEET, "Configuration des listes", features.AVAILABILITY_SHEET]
        if self.current_page in {"planning", "dashboard"}:
            sheets = list(previous_page_sheets(self))
            if RESOURCE_PROFILE_SHEET not in sheets:
                sheets.append(RESOURCE_PROFILE_SHEET)
            return sheets
        return previous_page_sheets(self)

    v16.resource_class_map = resource_class_map
    v16.recommend_resources = recommend_resources
    v16._open_recommendation_dialog = _open_recommendation_dialog

    ui_module.PlannerUI._render_content = render_content
    ui_module.PlannerUI._page_sheets = page_sheets
    ui_module.PlannerUI.render_resources = _render_resources
    ui_module.PlannerUI.render_planning = _render_planning
    v13._render_operational_planning = _render_planning
    v15._render_operational_planning_v15 = _render_planning
    v15_refinements._render_planning = _render_planning
    ui_module.PlannerUI._v16_refinements_installed = True
