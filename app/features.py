from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from nicegui import ui

from . import ui as ui_module
from .excel_repository import (
    ExcelRepository,
    MASTER_SHEETS,
    _as_matrix,
    _date_from_any,
)
from .services import effort_overlaps_day, week_days


AVAILABILITY_SHEET = "Disponibilites"
AVAILABILITY_TABLE = "DisponibilitesTable"
AVAILABILITY_HEADERS = [
    "ID",
    "Technicien",
    "Type",
    "DateDebut",
    "DateFin",
    "JoursSemaine",
    "HeureDebut",
    "HeureFin",
    "Note",
    "Actif",
]
AVAILABILITY_TYPES = ["Horaire standard", "Jour férié", "Vacances"]
WEEKDAY_LABELS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]


def _is_active(value: Any) -> bool:
    return str(value or "Oui").strip().lower() not in {"non", "no", "false", "0", "inactif"}


def _format_date(value: Any) -> str:
    parsed = _date_from_any(value)
    return parsed.isoformat() if parsed else ""


def _record_applies(record: dict[str, Any], day: date) -> bool:
    start = _date_from_any(record.get("DateDebut"))
    end = _date_from_any(record.get("DateFin"))
    if start and day < start:
        return False
    if end and day > end:
        return False
    return True


def _weekday_matches(record: dict[str, Any], day: date) -> bool:
    raw = str(record.get("JoursSemaine") or "").strip()
    if not raw:
        return True
    tokens = {part.strip().lower() for part in raw.replace(";", ",").split(",") if part.strip()}
    return WEEKDAY_LABELS[day.weekday()].lower() in tokens


def _ensure_availability_sheet(repo: ExcelRepository) -> None:
    repo._ensure_sheet_table(AVAILABILITY_SHEET, AVAILABILITY_HEADERS, AVAILABILITY_TABLE)
    MASTER_SHEETS.add(AVAILABILITY_SHEET)
    repo.save()


def availability_records(repo: ExcelRepository) -> list[dict[str, Any]]:
    with repo._lock:
        _ensure_availability_sheet(repo)
        sheet = repo._book().sheets[AVAILABILITY_SHEET]
        matrix = _as_matrix(sheet.used_range.value)
        if not matrix:
            return []
        headers = matrix[0]
        records: list[dict[str, Any]] = []
        for excel_row, row in enumerate(matrix[1:], start=2):
            if not row or row[0] in (None, ""):
                continue
            item: dict[str, Any] = {"_row": excel_row}
            for idx, header in enumerate(headers):
                if header in (None, ""):
                    continue
                item[str(header)] = row[idx] if idx < len(row) else None
            item["DateDebut"] = _date_from_any(item.get("DateDebut"))
            item["DateFin"] = _date_from_any(item.get("DateFin"))
            records.append(item)
        return records


def add_availability(repo: ExcelRepository, values: dict[str, Any]) -> str:
    _ensure_availability_sheet(repo)
    identifier = f"DISP-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    payload = {header: None for header in AVAILABILITY_HEADERS}
    payload.update(values)
    payload["ID"] = identifier
    payload["Actif"] = payload.get("Actif") or "Oui"
    repo._append_dict_row(AVAILABILITY_SHEET, AVAILABILITY_HEADERS, payload, AVAILABILITY_TABLE)
    return identifier


def delete_availability(repo: ExcelRepository, row_number: int) -> None:
    with repo._lock:
        sheet = repo._book().sheets[AVAILABILITY_SHEET]
        sheet.range((row_number, 1), (row_number, len(AVAILABILITY_HEADERS))).clear_contents()
        repo.save()


def initialize_standard_schedules(repo: ExcelRepository) -> int:
    existing = availability_records(repo)
    existing_techs = {
        str(r.get("Technicien") or "").strip()
        for r in existing
        if str(r.get("Type") or "") == "Horaire standard" and _is_active(r.get("Actif"))
    }
    created = 0
    for tech in repo.technicians():
        name = tech["name"]
        if name in existing_techs:
            continue
        add_availability(
            repo,
            {
                "Technicien": name,
                "Type": "Horaire standard",
                "JoursSemaine": "Lun,Mar,Mer,Jeu,Ven",
                "HeureDebut": "08:00",
                "HeureFin": "16:00",
                "Note": "Horaire standard initialisé par l'application",
            },
        )
        created += 1
    return created


def availability_for_day(repo: ExcelRepository, technician: str, day: date) -> dict[str, Any]:
    records = [r for r in availability_records(repo) if _is_active(r.get("Actif"))]
    technician = str(technician or "").strip()

    for record in records:
        if str(record.get("Type") or "") != "Jour férié":
            continue
        target = str(record.get("Technicien") or "").strip()
        if target and target != technician:
            continue
        if _record_applies(record, day):
            return {
                "available": False,
                "reason": str(record.get("Note") or "Jour férié"),
                "hours": "",
                "type": "Jour férié",
            }

    for record in records:
        if str(record.get("Type") or "") != "Vacances":
            continue
        if str(record.get("Technicien") or "").strip() != technician:
            continue
        if _record_applies(record, day):
            return {
                "available": False,
                "reason": str(record.get("Note") or "Vacances"),
                "hours": "",
                "type": "Vacances",
            }

    standards = [
        r
        for r in records
        if str(r.get("Type") or "") == "Horaire standard"
        and str(r.get("Technicien") or "").strip() == technician
    ]
    if standards:
        matching = [r for r in standards if _record_applies(r, day) and _weekday_matches(r, day)]
        if not matching:
            return {
                "available": False,
                "reason": "Hors horaire standard",
                "hours": "",
                "type": "Horaire standard",
            }
        record = matching[0]
        start = str(record.get("HeureDebut") or "").strip()
        end = str(record.get("HeureFin") or "").strip()
        return {
            "available": True,
            "reason": "Horaire standard",
            "hours": f"{start}–{end}" if start or end else "",
            "type": "Horaire standard",
        }

    if day.weekday() >= 5:
        return {
            "available": False,
            "reason": "Fin de semaine",
            "hours": "",
            "type": "Horaire par défaut",
        }
    return {
        "available": True,
        "reason": "Horaire par défaut",
        "hours": "08:00–16:00",
        "type": "Horaire par défaut",
    }


def availability_conflicts(repo: ExcelRepository, technician: str, start_value: Any, end_value: Any) -> list[dict[str, Any]]:
    start = _date_from_any(start_value)
    end = _date_from_any(end_value) or start
    if not start or not end:
        return []
    if end < start:
        start, end = end, start
    conflicts: list[dict[str, Any]] = []
    cursor = start
    while cursor <= end:
        state = availability_for_day(repo, technician, cursor)
        if not state["available"]:
            conflicts.append({"date": cursor, **state})
        cursor += timedelta(days=1)
    return conflicts


def _project_data(repo: ExcelRepository) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    options: dict[str, str] = {}
    lookup: dict[str, dict[str, Any]] = {}
    for project in repo.projects(active_only=False):
        number = project.get("Numéro de Projet")
        if number in (None, ""):
            continue
        key = str(number)
        name = project.get("Nom de référence") or project.get("Description de l'appel d'offre") or ""
        client = project.get("Donneur d'ouvrage") or ""
        label_parts = [key]
        if name:
            label_parts.append(str(name))
        if client and str(client) not in str(name):
            label_parts.append(str(client))
        options[key] = " — ".join(label_parts)
        lookup[key] = project
    return options, lookup


def _open_request_dialog(self: ui_module.PlannerUI, demand: dict[str, Any] | None = None) -> None:
    self.interaction_lock = True
    editing = demand is not None
    project_options, project_lookup = _project_data(self.repo)
    competencies = self.repo.competencies()
    technicians = [t["name"] for t in self.repo.technicians()]

    initial_project = str(demand.get("NumeroProjet") or "") if demand else None
    if initial_project and initial_project not in project_options:
        project_options[initial_project] = f"{initial_project} — {demand.get('NomProjet') or ''}"

    with ui.dialog() as dialog, ui.card().classes("w-[820px] max-w-full"):
        ui.label(
            f"Modifier {demand.get('NoDemande')}" if editing else "Nouvelle demande de main-d'œuvre"
        ).classes("text-xl font-bold")
        if editing:
            ui.label(f"Statut actuel : {demand.get('Statut') or ''}").classes("text-sm muted")

        project = ui.select(
            project_options,
            label="Projet — taper pour rechercher par numéro, nom ou client",
            value=initial_project,
            with_input=True,
            clearable=True,
        ).classes("w-full")

        with ui.row().classes("w-full"):
            req_type = ui.select(
                ["Service", "Projet", "Interne"],
                label="Type",
                value=(demand.get("TypeDemande") if demand else "Projet") or "Projet",
            ).classes("flex-1")
            priority = ui.select(
                ["Urgent", "Élevée", "Normale", "Basse"],
                label="Priorité",
                value=(demand.get("Priorite") if demand else "Normale") or "Normale",
            ).classes("flex-1")

        with ui.row().classes("w-full"):
            start = ui.input(
                "Début souhaité",
                value=self._date_text(demand.get("DateDebutSouhaitee")) if demand else "",
            ).props("type=date").classes("flex-1")
            end = ui.input(
                "Fin souhaitée",
                value=self._date_text(demand.get("DateFinSouhaitee")) if demand else "",
            ).props("type=date").classes("flex-1")

        with ui.row().classes("w-full"):
            competency = ui.select(
                competencies,
                label="Compétence requise",
                value=demand.get("CompetencesRequises") if demand else None,
                with_input=True,
                clearable=True,
            ).classes("flex-1")
            technician = ui.select(
                technicians,
                label="Technicien proposé",
                value=demand.get("TechnicienPropose") if demand else None,
                with_input=True,
                clearable=True,
            ).classes("flex-1")

        with ui.row().classes("w-full"):
            resources = ui.number(
                "Nombre de ressources",
                value=(demand.get("NombreRessources") if demand else 1) or 1,
                min=1,
                step=1,
            ).classes("flex-1")
            hours = ui.number(
                "Temps estimé (h)",
                value=demand.get("TempsEstimeHeures") if demand else None,
                min=0,
                step=1,
            ).classes("flex-1")
            days_count = ui.number(
                "Temps estimé (jours)",
                value=demand.get("TempsEstimeJours") if demand else None,
                min=0,
                step=0.5,
            ).classes("flex-1")

        site = ui.input(
            "Site client / lieu",
            value=str((demand.get("SiteClient") or demand.get("Lieu") or "") if demand else ""),
        ).classes("w-full")
        description = ui.textarea(
            "Description",
            value=str(demand.get("Description") or "") if demand else "",
        ).classes("w-full")

        def build_payload() -> dict[str, Any]:
            selected = project_lookup.get(str(project.value), {})
            existing_name = demand.get("NomProjet") if demand else ""
            existing_client = demand.get("Client") if demand else ""
            existing_pm = demand.get("ChargeProjet") if demand else ""
            return {
                "NumeroProjet": project.value,
                "NomProjet": selected.get("Nom de référence")
                or selected.get("Description de l'appel d'offre")
                or existing_name
                or "",
                "Client": selected.get("Donneur d'ouvrage") or existing_client or "",
                "ChargeProjet": selected.get("Chargé de projet") or existing_pm or "",
                "TypeDemande": req_type.value,
                "Priorite": priority.value,
                "DateDebutSouhaitee": start.value,
                "DateFinSouhaitee": end.value,
                "Description": description.value,
                "SiteClient": site.value,
                "Lieu": site.value,
                "NombreRessources": resources.value,
                "CompetencesRequises": competency.value,
                "TempsEstimeHeures": hours.value,
                "TempsEstimeJours": days_count.value,
                "TechnicienPropose": technician.value,
            }

        def validate() -> bool:
            if not project.value or not start.value:
                ui.notify("Projet et date de début sont requis.", type="warning")
                return False
            if end.value and _date_from_any(end.value) and _date_from_any(start.value) and _date_from_any(end.value) < _date_from_any(start.value):
                ui.notify("La date de fin ne peut pas précéder la date de début.", type="warning")
                return False
            return True

        def save_edit() -> None:
            if not validate():
                return
            try:
                self.repo.update_demand(
                    str(demand["NoDemande"]),
                    build_payload(),
                    action="Modification",
                    comment="Demande modifiée dans l'application",
                )
                dialog.close()
                self._after_write("Demande mise à jour")
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        def save_draft() -> None:
            if not validate():
                return
            try:
                number = self.repo.create_demand(build_payload(), submit=False)
                dialog.close()
                self._after_write(f"{number} enregistré comme brouillon")
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        def submit_new() -> None:
            if not validate():
                return
            try:
                number = self.repo.create_demand(build_payload(), submit=True)
                dialog.close()
                self._after_write(f"{number} soumise pour approbation")
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        with ui.row().classes("w-full justify-end"):
            ui.button("Annuler", on_click=dialog.close).props("flat no-caps")
            if editing:
                ui.button("Enregistrer", icon="save", on_click=save_edit).props(
                    "unelevated no-caps color=primary"
                )
            else:
                ui.button("Brouillon", icon="save", on_click=save_draft).props("outline no-caps")
                ui.button("Soumettre", icon="send", on_click=submit_new).props(
                    "unelevated no-caps color=primary"
                )

    dialog.on("hide", lambda _: self._unlock())
    dialog.open()


def _open_new_request_dialog(self: ui_module.PlannerUI) -> None:
    _open_request_dialog(self, None)


def _open_edit_request_dialog(self: ui_module.PlannerUI, demand: dict[str, Any]) -> None:
    _open_request_dialog(self, demand)


def _render_availability(self: ui_module.PlannerUI) -> None:
    records = availability_records(self.repo)
    techs = [t["name"] for t in self.repo.technicians()]

    with ui.row().classes("w-full items-center"):
        with ui.column().classes("gap-0"):
            ui.label("Disponibilités").classes("text-2xl font-bold")
            ui.label("Horaires standards, jours fériés et vacances utilisés par la planification.").classes("muted")
        ui.space()
        ui.button("Initialiser horaires", icon="schedule", on_click=lambda: _initialize_schedules(self)).props(
            "outline no-caps"
        )
        ui.button("Horaire standard", icon="access_time", on_click=lambda: _availability_dialog(self, "Horaire standard")).props(
            "outline no-caps"
        )
        ui.button("Jour férié", icon="event_busy", on_click=lambda: _availability_dialog(self, "Jour férié")).props(
            "outline no-caps"
        )
        ui.button("Vacances", icon="beach_access", on_click=lambda: _availability_dialog(self, "Vacances")).props(
            "unelevated no-caps color=primary"
        )

    rows = []
    for record in records:
        rows.append(
            {
                "_row": record["_row"],
                "ID": record.get("ID"),
                "Technicien": record.get("Technicien") or "Tous",
                "Type": record.get("Type") or "",
                "Début": _format_date(record.get("DateDebut")),
                "Fin": _format_date(record.get("DateFin")),
                "Jours": record.get("JoursSemaine") or "",
                "Heures": "–".join(
                    value for value in [str(record.get("HeureDebut") or ""), str(record.get("HeureFin") or "")] if value
                ),
                "Note": record.get("Note") or "",
                "Actif": record.get("Actif") or "Oui",
            }
        )

    columns = [
        {"headerName": "Technicien", "field": "Technicien", "minWidth": 160},
        {"headerName": "Type", "field": "Type", "minWidth": 145},
        {"headerName": "Début", "field": "Début", "minWidth": 115},
        {"headerName": "Fin", "field": "Fin", "minWidth": 115},
        {"headerName": "Jours", "field": "Jours", "minWidth": 170},
        {"headerName": "Heures", "field": "Heures", "minWidth": 120},
        {"headerName": "Note", "field": "Note", "minWidth": 220},
        {"headerName": "Actif", "field": "Actif", "minWidth": 90},
    ]

    grid = ui.aggrid(
        {
            "columnDefs": columns,
            "rowData": rows,
            "rowSelection": "single",
            "defaultColDef": {"sortable": True, "filter": True, "resizable": True},
        }
    ).classes("w-full h-[470px]")

    async def delete_selected() -> None:
        selected = await grid.get_selected_row()
        if not selected:
            ui.notify("Sélectionne une ligne à supprimer.", type="warning")
            return
        try:
            delete_availability(self.repo, int(selected["_row"]))
            self._after_write("Disponibilité supprimée")
        except Exception as exc:
            ui.notify(str(exc), type="negative")

    with ui.row().classes("w-full items-center"):
        ui.button("Supprimer la sélection", icon="delete", on_click=delete_selected).props(
            "flat no-caps color=negative"
        )
        ui.label(
            "La feuille Disponibilites est aussi disponible dans Données Excel pour les corrections avancées."
        ).classes("text-xs muted")


def _initialize_schedules(self: ui_module.PlannerUI) -> None:
    try:
        count = initialize_standard_schedules(self.repo)
        self._after_write(
            f"{count} horaire(s) standard initialisé(s)" if count else "Tous les techniciens ont déjà un horaire standard"
        )
    except Exception as exc:
        ui.notify(str(exc), type="negative")


def _availability_dialog(self: ui_module.PlannerUI, availability_type: str) -> None:
    self.interaction_lock = True
    technicians = [t["name"] for t in self.repo.technicians()]

    with ui.dialog() as dialog, ui.card().classes("w-[650px] max-w-full"):
        ui.label(f"Ajouter — {availability_type}").classes("text-xl font-bold")

        technician = ui.select(
            technicians,
            label="Technicien" if availability_type != "Jour férié" else "Technicien (vide = tous)",
            with_input=True,
            clearable=True,
        ).classes("w-full")

        weekdays = None
        start_time = None
        end_time = None
        start_date = None
        end_date = None

        if availability_type == "Horaire standard":
            weekdays = ui.select(
                WEEKDAY_LABELS,
                label="Jours de la semaine",
                value=["Lun", "Mar", "Mer", "Jeu", "Ven"],
                multiple=True,
            ).classes("w-full")
            with ui.row().classes("w-full"):
                start_time = ui.input("Heure de début", value="08:00").props("type=time").classes("flex-1")
                end_time = ui.input("Heure de fin", value="16:00").props("type=time").classes("flex-1")
            with ui.row().classes("w-full"):
                start_date = ui.input("Valide à partir de (optionnel)").props("type=date").classes("flex-1")
                end_date = ui.input("Valide jusqu'au (optionnel)").props("type=date").classes("flex-1")
        else:
            with ui.row().classes("w-full"):
                start_date = ui.input("Date de début").props("type=date").classes("flex-1")
                end_date = ui.input("Date de fin").props("type=date").classes("flex-1")

        note = ui.input("Note / motif").classes("w-full")

        def save() -> None:
            if availability_type in {"Horaire standard", "Vacances"} and not technician.value:
                ui.notify("Sélectionne un technicien.", type="warning")
                return
            if availability_type != "Horaire standard" and not start_date.value:
                ui.notify("La date de début est requise.", type="warning")
                return
            if start_date and end_date and start_date.value and end_date.value:
                start_parsed = _date_from_any(start_date.value)
                end_parsed = _date_from_any(end_date.value)
                if start_parsed and end_parsed and end_parsed < start_parsed:
                    ui.notify("La date de fin ne peut pas précéder la date de début.", type="warning")
                    return
            try:
                add_availability(
                    self.repo,
                    {
                        "Technicien": technician.value,
                        "Type": availability_type,
                        "DateDebut": start_date.value if start_date else None,
                        "DateFin": (end_date.value or start_date.value) if end_date else None,
                        "JoursSemaine": ",".join(weekdays.value or []) if weekdays else None,
                        "HeureDebut": start_time.value if start_time else None,
                        "HeureFin": end_time.value if end_time else None,
                        "Note": note.value,
                        "Actif": "Oui",
                    },
                )
                dialog.close()
                self._after_write(f"{availability_type} ajouté")
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        with ui.row().classes("w-full justify-end"):
            ui.button("Annuler", on_click=dialog.close).props("flat no-caps")
            ui.button("Ajouter", icon="add", on_click=save).props("unelevated no-caps color=primary")

    dialog.on("hide", lambda _: self._unlock())
    dialog.open()


def _render_planning_with_availability(self: ui_module.PlannerUI) -> None:
    days = week_days(self.current_week)
    techs = self.repo.technicians()
    efforts = self.repo.efforts(include_closed=False)

    with ui.row().classes("w-full items-center"):
        with ui.column().classes("gap-0"):
            ui.label("Planification").classes("text-2xl font-bold")
            ui.label("Vue ressources — les indisponibilités sont intégrées directement dans le calendrier.").classes("muted")
        ui.space()
        ui.button(icon="chevron_left", on_click=self.previous_week).props("flat round")
        ui.button("Aujourd'hui", on_click=self.today_week).props("outline no-caps")
        ui.button(icon="chevron_right", on_click=self.next_week).props("flat round")
        ui.label(f"{days[0].strftime('%d %b')} – {days[-1].strftime('%d %b %Y')}").classes("font-semibold ml-2")

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
                    details = " · ".join(v for v in [tech.get("description"), tech.get("team")] if v)
                    ui.label(details or "Ressource").classes("text-xs muted")

                tech_efforts = [
                    e
                    for e in efforts
                    if str(e.get("Équipe/Technicien attitré") or "").strip() == name
                ]
                for day in days:
                    state = availability_for_day(self.repo, name, day)
                    classes = "day-cell gap-1"
                    if not state["available"]:
                        classes += " unavailable-cell"
                    elif day.weekday() >= 5:
                        classes += " weekend-cell"
                    with ui.column().classes(classes):
                        if state["available"] and state.get("hours"):
                            ui.label(state["hours"]).classes("text-[10px] availability-hours")
                        elif not state["available"]:
                            ui.label(state["reason"]).classes("text-[10px] unavailable-label")

                        day_efforts = [e for e in tech_efforts if effort_overlaps_day(e, day)]
                        if day_efforts and not state["available"]:
                            ui.label("⚠ Conflit disponibilité").classes("text-[10px] text-red-700 font-semibold")
                        for effort_index, effort in enumerate(day_efforts):
                            css = ui_module.PASTEL_CLASSES[(tech_index + effort_index) % len(ui_module.PASTEL_CLASSES)]
                            with ui.element("div").classes(f"shift-card {css}").on(
                                "click", lambda _, e=effort: self.open_effort_dialog(e)
                            ):
                                ui.label(
                                    f"{effort.get('N° projet') or '—'} · {effort.get('Projet') or ''}"
                                ).classes("text-xs font-semibold")
                                ui.label(
                                    str(effort.get("Précision") or effort.get("Compétence") or "Affectation")
                                ).classes("text-xs")
                                effort_hours = effort.get("Efforts Prévus")
                                if effort_hours:
                                    ui.label(f"{effort_hours:g} h").classes("text-[11px] muted")


def install_features() -> None:
    if getattr(ui_module.PlannerUI, "_v12_features_installed", False):
        return

    MASTER_SHEETS.add(AVAILABILITY_SHEET)

    original_ensure = ExcelRepository.ensure_app_sheets

    def ensure_app_sheets(self: ExcelRepository) -> None:
        original_ensure(self)
        _ensure_availability_sheet(self)

    ExcelRepository.ensure_app_sheets = ensure_app_sheets

    if not any(item[0] == "availability" for item in ui_module.NAV_ITEMS):
        settings_index = next(
            (index for index, item in enumerate(ui_module.NAV_ITEMS) if item[0] == "settings"),
            len(ui_module.NAV_ITEMS),
        )
        ui_module.NAV_ITEMS.insert(settings_index, ("availability", "event_available", "Disponibilités"))

    original_render_content = ui_module.PlannerUI._render_content
    original_page_sheets = ui_module.PlannerUI._page_sheets
    original_request_actions = ui_module.PlannerUI._request_actions
    original_setup_style = ui_module.PlannerUI._setup_style

    def setup_style(self: ui_module.PlannerUI) -> None:
        original_setup_style(self)
        ui.add_head_html(
            """
            <style>
              .unavailable-cell { background:#f3f4f6 !important; background-image:repeating-linear-gradient(135deg, transparent, transparent 8px, rgba(120,120,120,.06) 8px, rgba(120,120,120,.06) 16px); }
              .unavailable-label { color:#7f1d1d; font-weight:600; }
              .availability-hours { color:#2e7d32; font-weight:600; }
            </style>
            """
        )

    def render_content(self: ui_module.PlannerUI) -> None:
        if self.current_page == "availability":
            self.render_availability()
            return
        original_render_content(self)

    def page_sheets(self: ui_module.PlannerUI) -> list[str]:
        if self.current_page == "availability":
            return [AVAILABILITY_SHEET, "Configuration des listes"]
        sheets = original_page_sheets(self)
        if self.current_page == "planning" and AVAILABILITY_SHEET not in sheets:
            sheets = [*sheets, AVAILABILITY_SHEET]
        return sheets

    def request_actions(self: ui_module.PlannerUI) -> None:
        original_request_actions(self)
        if not self.selected_request:
            return
        demand = next(
            (d for d in self.repo.demands() if d.get("NoDemande") == self.selected_request),
            None,
        )
        if not demand or str(demand.get("Statut") or "") in {"Annulée", "Fermé"}:
            return
        with ui.row().classes("w-full mt-2"):
            ui.button(
                "Modifier la demande",
                icon="edit",
                on_click=lambda: self.open_edit_request_dialog(demand),
            ).props("outline no-caps")

    ui_module.PlannerUI._setup_style = setup_style
    ui_module.PlannerUI._render_content = render_content
    ui_module.PlannerUI._page_sheets = page_sheets
    ui_module.PlannerUI._request_actions = request_actions
    ui_module.PlannerUI.open_new_request_dialog = _open_new_request_dialog
    ui_module.PlannerUI.open_edit_request_dialog = _open_edit_request_dialog
    ui_module.PlannerUI.render_availability = _render_availability
    ui_module.PlannerUI.render_planning = _render_planning_with_availability
    ui_module.PlannerUI._v12_features_installed = True
