from __future__ import annotations

from typing import Any

from nicegui import ui

from . import ui as ui_module
from . import v13, v14
from .excel_repository import ExcelRepository, _date_from_any
from .v14_engine import rebuild_allocations


def _same_effort_row(value: Any, effort_row: int) -> bool:
    try:
        return int(float(value)) == int(effort_row)
    except (TypeError, ValueError):
        return False


def _linked_demands_for_effort(repo: ExcelRepository, effort_row: int) -> list[dict[str, Any]]:
    """Retrouve les demandes liées directement ou par un segment.

    Certains classeurs créés pendant la V1.3 possèdent un SourceEffortRow dans
    SegmentsMO alors que la demande d'origine n'a pas encore ce lien. Le Gantt
    récupère aussi ces demandes afin de permettre leur modification.
    """
    demands = {
        str(row.get("NoDemande") or "").strip(): row
        for row in repo.demands()
        if str(row.get("NoDemande") or "").strip()
    }
    numbers: list[str] = []

    for demand in demands.values():
        if _same_effort_row(demand.get(v13.SOURCE_EFFORT_FIELD), effort_row):
            number = str(demand.get("NoDemande") or "").strip()
            if number and number not in numbers:
                numbers.append(number)

    for segment in v13.segment_records(repo):
        if not _same_effort_row(segment.get("SourceEffortRow"), effort_row):
            continue
        number = str(segment.get("NoDemande") or "").strip()
        if number and number in demands and number not in numbers:
            numbers.append(number)

    return [demands[number] for number in numbers if number in demands]


def _demand_edit_form(
    self: ui_module.PlannerUI,
    demand: dict[str, Any],
    effort_row: int,
    parent_dialog: Any,
) -> None:
    number = str(demand.get("NoDemande") or "")
    status = str(demand.get("Statut") or "")
    locked = status in {"Annulée", "Fermé"}

    competence_options = list(self.repo.competencies())
    current_competence = str(demand.get("CompetencesRequises") or "").strip() or None
    if current_competence and current_competence not in competence_options:
        competence_options.append(current_competence)

    technician_options = [row["name"] for row in self.repo.technicians()]
    current_technician = str(demand.get("TechnicienPropose") or "").strip() or None
    if current_technician and current_technician not in technician_options:
        technician_options.append(current_technician)

    with ui.card().classes("w-full border border-gray-200 shadow-none"):
        with ui.row().classes("w-full items-center"):
            with ui.column().classes("gap-0"):
                ui.label(number).classes("font-semibold text-base")
                ui.label(
                    f"{status or '—'} · {demand.get('NumeroProjet') or '—'} · {demand.get('NomProjet') or ''}"
                ).classes("text-xs muted")
            ui.space()
            ui.button(
                "Segments",
                icon="view_timeline",
                on_click=lambda d=demand: v14._segments_from_medium_term(self, parent_dialog, d),
            ).props("flat dense no-caps")

        if locked:
            ui.label("Cette demande est verrouillée parce qu'elle est fermée ou annulée.").classes(
                "text-sm text-amber-700"
            )
            return

        with ui.row().classes("w-full"):
            req_type = ui.select(
                ["Service", "Projet", "Interne"],
                label="Type",
                value=str(demand.get("TypeDemande") or "Projet"),
            ).classes("flex-1")
            priority = ui.select(
                ["Urgent", "Élevée", "Normale", "Basse"],
                label="Priorité",
                value=str(demand.get("Priorite") or "Normale"),
            ).classes("flex-1")

        with ui.row().classes("w-full"):
            start = ui.input(
                "Début souhaité",
                value=self._date_text(demand.get("DateDebutSouhaitee")),
            ).props("type=date").classes("flex-1")
            end = ui.input(
                "Fin souhaitée",
                value=self._date_text(demand.get("DateFinSouhaitee")),
            ).props("type=date").classes("flex-1")

        with ui.row().classes("w-full"):
            competence = ui.select(
                competence_options,
                label="Compétence requise",
                value=current_competence,
                with_input=True,
                clearable=True,
            ).classes("flex-1")
            technician = ui.select(
                technician_options,
                label="Technicien proposé",
                value=current_technician,
                with_input=True,
                clearable=True,
            ).classes("flex-1")

        with ui.row().classes("w-full"):
            resources = ui.number(
                "Nombre de ressources",
                value=v13._number(demand.get("NombreRessources")) or 1,
                min=1,
                step=1,
            ).classes("flex-1")
            hours = ui.number(
                "Temps estimé (h)",
                value=v13._number(demand.get("TempsEstimeHeures")) or None,
                min=0,
                step=0.5,
            ).classes("flex-1")
            days_count = ui.number(
                "Temps estimé (jours)",
                value=v13._number(demand.get("TempsEstimeJours")) or None,
                min=0,
                step=0.5,
            ).classes("flex-1")

        site = ui.input(
            "Site client / lieu",
            value=str(demand.get("SiteClient") or demand.get("Lieu") or ""),
        ).classes("w-full")
        description = ui.textarea(
            "Description",
            value=str(demand.get("Description") or ""),
        ).classes("w-full")

        def save() -> None:
            start_date = _date_from_any(start.value)
            end_date = _date_from_any(end.value) or start_date
            if not start_date:
                ui.notify("La date de début est requise.", type="warning")
                return
            if end_date and end_date < start_date:
                ui.notify("La date de fin ne peut pas précéder la date de début.", type="warning")
                return
            try:
                self.repo.update_demand(
                    number,
                    {
                        "TypeDemande": req_type.value,
                        "Priorite": priority.value,
                        "DateDebutSouhaitee": start.value,
                        "DateFinSouhaitee": end.value,
                        "CompetencesRequises": competence.value,
                        "TechnicienPropose": technician.value,
                        "NombreRessources": resources.value,
                        "TempsEstimeHeures": hours.value,
                        "TempsEstimeJours": days_count.value,
                        "SiteClient": site.value,
                        "Lieu": site.value,
                        "Description": description.value,
                        v13.SOURCE_EFFORT_FIELD: effort_row,
                    },
                    action="Modification",
                    comment="Demande modifiée depuis la planification moyen terme",
                )
                rebuild_allocations(self.repo)
                self._signature = self._signature_for_current_page()
                ui.notify(f"{number} mise à jour", type="positive")
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        with ui.row().classes("w-full justify-end"):
            ui.button("Enregistrer les modifications", icon="save", on_click=save).props(
                "unelevated no-caps color=primary"
            )


def _open_effort_macro_dialog_fixed(
    self: ui_module.PlannerUI,
    effort: dict[str, Any],
) -> None:
    self.interaction_lock = True
    row = int(effort.get("_row") or 0)
    linked = _linked_demands_for_effort(self.repo, row)
    total = v13._number(effort.get("Efforts Prévus"))
    detailed = v13._segment_hours_for_effort(self.repo, row)

    with ui.dialog() as dialog, ui.card().classes("w-[900px] max-w-[95vw] max-h-[90vh]"):
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
            ui.label(
                "Aucune demande MO liée. Tu peux en créer une avec les boutons ci-dessous."
            ).classes("text-sm muted")
        else:
            ui.label(
                "Les demandes liées sont modifiables directement ici. Le bouton Nouvelle demande reste disponible pour ajouter un besoin distinct."
            ).classes("text-xs muted")
            with ui.column().classes("w-full gap-3 max-h-[55vh] overflow-y-auto pr-2"):
                for demand in linked:
                    _demand_edit_form(self, demand, row, dialog)

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


def install_v14_fixes() -> None:
    if getattr(ui_module.PlannerUI, "_v14_fixes_installed", False):
        return

    # Le Gantt V1.3 appelle v13._open_effort_macro_dialog au moment du clic.
    # On remplace donc cette cible après l'installation de la V1.4.
    v14._open_effort_macro_dialog_v14 = _open_effort_macro_dialog_fixed
    v13._open_effort_macro_dialog = _open_effort_macro_dialog_fixed
    ui_module.PlannerUI._v14_fixes_installed = True
