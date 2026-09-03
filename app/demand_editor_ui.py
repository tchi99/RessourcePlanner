from __future__ import annotations

from typing import Any

from nicegui import ui

from . import ui as ui_module
from .application.runtime_services import demand_service
from .bugfixes import schedulable_technicians
from .excel_repository import _date_from_any
from .v15_refinements import (
    CONFIRMATION_OPTIONS,
    DEMAND_CONFIRMATION_FIELD,
    demand_confirmation,
)


def _project_data(repo: Any) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    """Build the project selector without coupling demand editing to legacy features."""
    options: dict[str, str] = {}
    lookup: dict[str, dict[str, Any]] = {}
    for project in repo.projects(active_only=False):
        number = project.get("Numéro de Projet")
        if number in (None, ""):
            continue
        key = str(number)
        name = (
            project.get("Nom de référence")
            or project.get("Description de l'appel d'offre")
            or ""
        )
        client = project.get("Donneur d'ouvrage") or ""
        label_parts = [key]
        if name:
            label_parts.append(str(name))
        if client and str(client) not in str(name):
            label_parts.append(str(client))
        options[key] = " — ".join(label_parts)
        lookup[key] = project
    return options, lookup


def _work_package_data(repo: Any) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    """Build stable WorkPackage choices from medium-term effort rows.

    The selector carries IDEffort/SourceEffortID rather than an Excel row number so
    the same demand link survives the SQL cutover.
    """

    options: dict[str, str] = {}
    lookup: dict[str, dict[str, Any]] = {}
    for effort in repo.efforts(include_closed=True):
        identifier = str(effort.get("IDEffort") or "").strip()
        if not identifier:
            continue
        project_number = str(effort.get("N° projet") or "").strip()
        name = str(effort.get("Projet") or effort.get("Description") or "").strip()
        start = _date_from_any(effort.get("Date de début"))
        end = _date_from_any(effort.get("Date de fin"))
        label_parts = [project_number or "Projet —", name or identifier]
        if start:
            period = start.strftime("%d/%m/%Y")
            if end:
                period += f" → {end.strftime('%d/%m/%Y')}"
            label_parts.append(period)
        options[identifier] = " — ".join(part for part in label_parts if part)
        lookup[identifier] = effort
    return options, lookup


def _request_dialog(
    self: ui_module.PlannerUI,
    demand: dict[str, Any] | None = None,
) -> None:
    """Open the authoritative demand create/edit dialog.

    UI concerns live here. Both creation and editing cross ``DemandService`` so
    workflow ownership stays in the application layer instead of NiceGUI or Excel.
    """
    self.interaction_lock = True
    editing = demand is not None
    project_options, project_lookup = _project_data(self.repo)
    work_package_options, work_package_lookup = _work_package_data(self.repo)
    competencies = self.repo.competencies()
    technicians = [row["name"] for row in schedulable_technicians(self.repo)]

    initial_project = str(demand.get("NumeroProjet") or "") if demand else None
    if initial_project and initial_project not in project_options:
        project_options[initial_project] = (
            f"{initial_project} — {demand.get('NomProjet') or ''}"
        )
    initial_work_package = (
        str(demand.get("SourceEffortID") or "").strip() if demand else ""
    ) or None
    if initial_work_package and initial_work_package not in work_package_options:
        work_package_options[initial_work_package] = initial_work_package

    with ui.dialog() as dialog, ui.card().classes("w-[840px] max-w-full"):
        ui.label(
            f"Modifier {demand.get('NoDemande')}"
            if editing
            else "Nouvelle demande de main-d'œuvre"
        ).classes("text-xl font-bold")
        if editing:
            ui.label(f"Statut actuel : {demand.get('Statut') or ''}").classes(
                "text-sm muted"
            )

        project = ui.select(
            project_options,
            label="Projet — taper pour rechercher par numéro, nom ou client",
            value=initial_project,
            with_input=True,
            clearable=True,
        ).classes("w-full")

        work_package = ui.select(
            work_package_options,
            label="Plage moyen terme / WorkPackage",
            value=initial_work_package,
            with_input=True,
            clearable=True,
        ).classes("w-full")
        ui.label(
            "Optionnel · le lien utilise l'identifiant stable de la plage moyen terme."
        ).classes("text-xs muted -mt-2")

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
            confirmation = ui.select(
                CONFIRMATION_OPTIONS,
                label="Niveau de confirmation",
                value=demand_confirmation(demand),
            ).classes("flex-1")

        with ui.row().classes("w-full"):
            start = ui.input(
                "Début souhaité",
                value=(
                    self._date_text(demand.get("DateDebutSouhaitee"))
                    if demand
                    else ""
                ),
            ).props("type=date").classes("flex-1")
            end = ui.input(
                "Fin souhaitée",
                value=(
                    self._date_text(demand.get("DateFinSouhaitee"))
                    if demand
                    else ""
                ),
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
            value=str(
                (demand.get("SiteClient") or demand.get("Lieu") or "")
                if demand
                else ""
            ),
        ).classes("w-full")
        description = ui.textarea(
            "Description",
            value=str(demand.get("Description") or "") if demand else "",
        ).classes("w-full")

        def payload() -> dict[str, Any]:
            selected = project_lookup.get(str(project.value), {})
            return {
                "NumeroProjet": project.value,
                "NomProjet": selected.get("Nom de référence")
                or selected.get("Description de l'appel d'offre")
                or (demand.get("NomProjet") if demand else "")
                or "",
                "Client": selected.get("Donneur d'ouvrage")
                or (demand.get("Client") if demand else "")
                or "",
                "ChargeProjet": selected.get("Chargé de projet")
                or (demand.get("ChargeProjet") if demand else "")
                or "",
                "SourceEffortID": work_package.value,
                "TypeDemande": req_type.value,
                "Priorite": priority.value,
                DEMAND_CONFIRMATION_FIELD: confirmation.value or "Confirmée",
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
            start_date = _date_from_any(start.value)
            end_date = _date_from_any(end.value)
            if start_date and end_date and end_date < start_date:
                ui.notify(
                    "La date de fin ne peut pas précéder la date de début.",
                    type="warning",
                )
                return False
            if work_package.value:
                selected_effort = work_package_lookup.get(str(work_package.value))
                if selected_effort is not None:
                    effort_project = str(selected_effort.get("N° projet") or "").strip()
                    if effort_project and effort_project != str(project.value or "").strip():
                        ui.notify(
                            "La plage moyen terme sélectionnée n'appartient pas au projet choisi.",
                            type="warning",
                        )
                        return False
            return True

        def save_edit() -> None:
            if not validate():
                return
            try:
                reapproval_required = demand_service(self.repo).modify(
                    str(demand["NoDemande"]),
                    payload(),
                    comment="Demande modifiée dans l'application",
                )
                dialog.close()
                message = "Demande mise à jour"
                if reapproval_required:
                    message += " · nouvelle approbation requise"
                self._after_write(message)
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        def save_draft() -> None:
            if not validate():
                return
            try:
                number = demand_service(self.repo).create(payload(), submit=False)
                dialog.close()
                self._after_write(f"{number} enregistré comme brouillon")
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        def submit_new() -> None:
            if not validate():
                return
            try:
                number = demand_service(self.repo).create(payload(), submit=True)
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
                ui.button("Brouillon", icon="save", on_click=save_draft).props(
                    "outline no-caps"
                )
                ui.button("Soumettre", icon="send", on_click=submit_new).props(
                    "unelevated no-caps color=primary"
                )

    dialog.on("hide", lambda _: self._unlock())
    dialog.open()


def _open_new_request_dialog(self: ui_module.PlannerUI) -> None:
    _request_dialog(self)


def _open_edit_request_dialog(
    self: ui_module.PlannerUI,
    demand: dict[str, Any],
) -> None:
    _request_dialog(self, demand)


def install_demand_editor_ui() -> None:
    """Install the authoritative create/edit demand UI after all legacy installers."""
    if getattr(ui_module.PlannerUI, "_demand_editor_ui_installed", False):
        return

    ui_module.PlannerUI.open_new_request_dialog = _open_new_request_dialog
    ui_module.PlannerUI.open_edit_request_dialog = _open_edit_request_dialog
    ui_module.PlannerUI._demand_editor_ui_installed = True
