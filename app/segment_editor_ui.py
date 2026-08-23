from __future__ import annotations

from typing import Any

from nicegui import ui

from .application.runtime_services import segment_service
from .bugfixes import schedulable_technicians
from .excel_repository import _date_from_any
from .segment_repository import SEGMENT_STATUSES, number


PLAN_TYPES = ["Flexible", "Fixe"]
PRIORITIES = ["Urgent", "Élevée", "Normale", "Basse"]
SEGMENT_OVERTIME_FIELD = "HorsHoraireAutorise"
SOURCE_EFFORT_FIELD = "SourceEffortRow"


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "oui", "x"}


def _segment_plan_type(segment: dict[str, Any] | None) -> str:
    value = str((segment or {}).get("TypePlanification") or "Flexible").strip()
    return value if value in PLAN_TYPES else "Flexible"


def _norm_project(value: Any) -> str:
    if value in (None, ""):
        return ""
    text = str(value).strip()
    try:
        numeric = float(text.replace(",", "."))
        if numeric.is_integer():
            return str(int(numeric))
    except (TypeError, ValueError):
        pass
    return text.lower()


def _demand_options(repo: Any) -> dict[str, str]:
    options: dict[str, str] = {}
    for demand in repo.demands():
        if str(demand.get("Statut") or "") not in {
            "En planification",
            "Soumise",
            "À corriger",
        }:
            continue
        identifier = str(demand.get("NoDemande") or "")
        if identifier:
            options[identifier] = (
                f"{identifier} — {demand.get('NumeroProjet') or '—'} · "
                f"{demand.get('NomProjet') or ''}"
            )
    return options


def _effort_options(repo: Any, project_number: Any | None = None) -> dict[str, str]:
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
            f" · {dates} · {number(effort.get('Efforts Prévus')):g} h"
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


def open_segment_editor(
    owner: Any,
    *,
    segment: dict[str, Any] | None = None,
    demand_number: str | None = None,
) -> None:
    """Open the authoritative V1.8 segment editor through SegmentService."""
    owner.interaction_lock = True
    editing = segment is not None
    demands = {
        str(row.get("NoDemande") or ""): row
        for row in owner.repo.demands()
    }
    selected_number = (
        str(segment.get("NoDemande") or "")
        if segment
        else str(demand_number or "")
    )
    demand_options = _demand_options(owner.repo)
    if selected_number and selected_number not in demand_options:
        selected = demands.get(selected_number, {})
        demand_options[selected_number] = (
            f"{selected_number} — {selected.get('NumeroProjet') or '—'} · "
            f"{selected.get('NomProjet') or ''}"
        )
    current_demand = demands.get(selected_number, {})

    tech_options = [row["name"] for row in schedulable_technicians(owner.repo)]
    competence_options = list(owner.repo.competencies())
    effort_options = _effort_options(
        owner.repo,
        current_demand.get("NumeroProjet") if current_demand else None,
    )
    inherited_source = (
        _source_effort_for_demand(current_demand) if current_demand else None
    )

    source_value: Any = inherited_source
    if segment and segment.get(SOURCE_EFFORT_FIELD) not in (None, ""):
        try:
            source_value = str(int(float(segment.get(SOURCE_EFFORT_FIELD))))
        except (TypeError, ValueError):
            source_value = str(segment.get(SOURCE_EFFORT_FIELD))
    if source_value and source_value not in effort_options:
        effort_options.update(_effort_options(owner.repo))

    initial_competence = (
        str(segment.get("CompetenceRequise") or "")
        if segment
        else str(current_demand.get("CompetencesRequises") or "")
    ) or None
    if initial_competence and initial_competence not in competence_options:
        competence_options.append(initial_competence)

    initial_tech = (
        str(segment.get("Technicien") or "")
        if segment
        else str(current_demand.get("TechnicienPropose") or "")
    ).strip()
    initial_tech = initial_tech if initial_tech in tech_options else None

    with ui.dialog() as dialog, ui.card().classes("w-[840px] max-w-full"):
        ui.label(
            f"Modifier {segment.get('IDSegment')}" if editing else "Nouveau segment"
        ).classes("text-xl font-bold")
        ui.label(
            "Le technicien est facultatif. Le travail hors horaire au niveau du segment "
            "autorise le moteur à placer le reliquat en soirée, fin de semaine ou jour férié."
        ).classes("text-xs muted")

        demand_select = ui.select(
            demand_options,
            label="Demande MO",
            value=selected_number or None,
            with_input=True,
            clearable=False,
        ).classes("w-full")
        if selected_number:
            demand_select.props("readonly")
            if editing and current_demand:
                demand_select.props("append-icon=open_in_new")
                demand_select.on(
                    "click:append",
                    lambda _event: owner.open_edit_request_dialog(current_demand),
                )
                demand_select.tooltip("Ouvrir et modifier la demande associée")

        with ui.row().classes("w-full"):
            technician = ui.select(
                tech_options,
                label="Technicien (optionnel)",
                value=initial_tech,
                with_input=True,
                clearable=True,
            ).classes("flex-1")
            competence = ui.select(
                competence_options,
                label="Compétence requise",
                value=initial_competence,
                with_input=True,
                clearable=True,
            ).classes("flex-1")

        with ui.row().classes("w-full"):
            planning_type = ui.select(
                PLAN_TYPES,
                label="Type de planification",
                value=_segment_plan_type(segment),
            ).classes("flex-1")
            priority = ui.select(
                PRIORITIES,
                label="Priorité",
                value=(
                    str(segment.get("Priorite") or "")
                    if segment
                    else str(current_demand.get("Priorite") or "Normale")
                )
                or "Normale",
            ).classes("flex-1")
            status = ui.select(
                SEGMENT_STATUSES,
                label="Statut",
                value=(
                    str(segment.get("Statut") or "")
                    if segment
                    else ("Planifié" if initial_tech else "À assigner")
                )
                or "À assigner",
            ).classes("flex-1")

        with ui.row().classes("w-full"):
            start = ui.input(
                "Début",
                value=(
                    owner._date_text(segment.get("DateDebut"))
                    if segment
                    else owner._date_text(current_demand.get("DateDebutSouhaitee"))
                ),
            ).props("type=date").classes("flex-1")
            end = ui.input(
                "Fin",
                value=(
                    owner._date_text(segment.get("DateFin"))
                    if segment
                    else owner._date_text(current_demand.get("DateFinSouhaitee"))
                ),
            ).props("type=date").classes("flex-1")
            hours = ui.number(
                "Heures prévues",
                value=(
                    number(segment.get("HeuresPrevues"))
                    if segment
                    else (number(current_demand.get("TempsEstimeHeures")) or None)
                ),
                min=0.5,
                step=0.5,
            ).classes("flex-1")

        overtime_allowed = ui.checkbox(
            "Autoriser le segment à utiliser du travail hors horaire standard si la capacité normale est insuffisante",
            value=_truthy((segment or {}).get(SEGMENT_OVERTIME_FIELD)),
        )

        source = ui.select(
            effort_options,
            label="Planification moyen terme liée (optionnel)",
            value=source_value,
            with_input=True,
            clearable=True,
        ).classes("w-full")
        description = ui.input(
            "Description / précision",
            value=(
                str(segment.get("Description") or "")
                if segment
                else str(current_demand.get("Description") or "")
            ),
        ).classes("w-full")

        def validate() -> bool:
            if not demand_select.value:
                ui.notify("Sélectionne une demande.", type="warning")
                return False
            start_date = _date_from_any(start.value)
            end_date = _date_from_any(end.value) or start_date
            if not start_date:
                ui.notify("La date de début est requise.", type="warning")
                return False
            if end_date and end_date < start_date:
                ui.notify("La date de fin ne peut pas précéder la date de début.", type="warning")
                return False
            if number(hours.value) <= 0:
                ui.notify("Les heures prévues doivent être supérieures à zéro.", type="warning")
                return False
            if not competence.value:
                ui.notify("La compétence requise est nécessaire.", type="warning")
                return False
            return True

        def build_payload() -> dict[str, Any]:
            demand = demands.get(str(demand_select.value or ""), {})
            source_row: Any = source.value
            if source_row not in (None, ""):
                try:
                    source_row = int(float(source_row))
                except (TypeError, ValueError):
                    pass
            tech = str(technician.value or "").strip()
            chosen_status = str(status.value or "")
            if not tech and chosen_status not in {"Annulé", "Terminé"}:
                chosen_status = "À assigner"
            elif tech and chosen_status == "À assigner":
                chosen_status = "Planifié"
            return {
                "NoDemande": demand_select.value,
                "NumeroProjet": demand.get("NumeroProjet"),
                "NomProjet": demand.get("NomProjet"),
                "Technicien": tech or None,
                "DateDebut": start.value,
                "DateFin": end.value or start.value,
                "HeuresPrevues": hours.value,
                "Statut": chosen_status,
                "Description": description.value,
                SOURCE_EFFORT_FIELD: source_row,
                "CompetenceRequise": competence.value,
                "TypePlanification": planning_type.value or "Flexible",
                "Priorite": priority.value or "Normale",
                SEGMENT_OVERTIME_FIELD: "Oui" if overtime_allowed.value else "Non",
            }

        def save() -> None:
            if not validate():
                return
            try:
                service = segment_service(owner.repo)
                data = build_payload()
                if editing:
                    summary = service.update(str(segment["IDSegment"]), data)
                    message = f"{segment['IDSegment']} mis à jour"
                else:
                    identifier, summary = service.create(data)
                    message = f"{identifier} créé"
                dialog.close()
                if summary.get("unallocated_hours", 0) > 0:
                    message += (
                        f" · {summary['unallocated_hours']:g} h nécessitent du hors horaire"
                    )
                owner._after_write(message)
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        def cancel_segment() -> None:
            try:
                service = segment_service(owner.repo)
                service.cancel(str(segment["IDSegment"]))
                dialog.close()
                owner._after_write(f"{segment['IDSegment']} annulé")
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        with ui.row().classes("w-full justify-end"):
            ui.button("Annuler", on_click=dialog.close).props("flat no-caps")
            if editing and str(segment.get("Statut") or "") != "Annulé":
                ui.button(
                    "Annuler le segment",
                    icon="cancel",
                    on_click=cancel_segment,
                ).props("flat no-caps color=negative")
            ui.button("Enregistrer", icon="save", on_click=save).props(
                "unelevated no-caps color=primary"
            )

    dialog.on("hide", lambda _: owner._unlock())
    dialog.open()
