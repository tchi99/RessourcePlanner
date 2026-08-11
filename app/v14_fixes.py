from __future__ import annotations

from typing import Any

from nicegui import ui

from . import ui as ui_module
from . import v13, v14
from .excel_repository import EFFORT_STATUSES, ExcelRepository, _date_from_any


def _same_effort_row(value: Any, effort_row: int) -> bool:
    try:
        return int(float(value)) == int(effort_row)
    except (TypeError, ValueError):
        return False


def _linked_demands_for_effort(repo: ExcelRepository, effort_row: int) -> list[dict[str, Any]]:
    """Retrouve les demandes liées directement ou par un segment.

    Le lien par segment permet de continuer à reconnaître les données produites pendant
    la V1.3, même si SourceEffortRow n'avait pas encore été écrit dans DemandesMO.
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


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in {
        "oui",
        "yes",
        "true",
        "1",
        "x",
        "planifié",
        "fermé",
    }


def _open_effort_macro_dialog_fixed(
    self: ui_module.PlannerUI,
    effort: dict[str, Any],
) -> None:
    """Édite la ligne Liste_Effort sélectionnée, pas la demande MO liée."""
    self.interaction_lock = True
    row = int(effort.get("_row") or 0)
    linked = _linked_demands_for_effort(self.repo, row)
    total = v13._number(effort.get("Efforts Prévus"))
    detailed = v13._segment_hours_for_effort(self.repo, row)

    competence_options = list(self.repo.competencies())
    current_competence = str(effort.get("Compétence") or "").strip() or None
    if current_competence and current_competence not in competence_options:
        competence_options.append(current_competence)

    current_status = str(effort.get("Status") or "").strip() or None
    status_options = list(EFFORT_STATUSES)
    if current_status and current_status not in status_options:
        status_options.append(current_status)

    with ui.dialog() as dialog, ui.card().classes("w-[900px] max-w-[95vw] max-h-[92vh]"):
        with ui.row().classes("w-full items-center"):
            with ui.column().classes("gap-0"):
                ui.label("Modifier la planification moyen terme").classes("text-xl font-bold")
                ui.label(
                    f"Ligne {row} de Liste_Effort · {effort.get('N° projet') or '—'} · "
                    f"{effort.get('Projet') or ''}"
                ).classes("text-sm muted")
            ui.space()
            ui.label(
                f"Segments liés : {detailed:g} h · reste macro : {max(total - detailed, 0):g} h"
            ).classes("text-xs muted")

        ui.label(
            "Cette section modifie directement la ligne de Liste_Effort. Les demandes et segments déjà créés "
            "ne sont pas écrasés automatiquement."
        ).classes("text-xs text-amber-700")

        with ui.column().classes("w-full gap-3 max-h-[62vh] overflow-y-auto pr-2"):
            with ui.card().classes("w-full border border-gray-200 shadow-none"):
                ui.label("Planification macro").classes("font-semibold")

                with ui.row().classes("w-full"):
                    start = ui.input(
                        "Date de début",
                        value=self._date_text(effort.get("Date de début")),
                    ).props("type=date").classes("flex-1")
                    end = ui.input(
                        "Date de fin",
                        value=self._date_text(effort.get("Date de fin")),
                    ).props("type=date").classes("flex-1")
                    hours = ui.number(
                        "Efforts prévus (h)",
                        value=total or None,
                        min=0,
                        step=0.5,
                    ).classes("flex-1")

                with ui.row().classes("w-full"):
                    assigned = ui.input(
                        "Équipe / technicien attitré",
                        value=str(effort.get("Équipe/Technicien attitré") or ""),
                    ).classes("flex-1")
                    competence = ui.select(
                        competence_options,
                        label="Compétence",
                        value=current_competence,
                        with_input=True,
                        clearable=True,
                    ).classes("flex-1")
                    status = ui.select(
                        status_options,
                        label="Statut",
                        value=current_status,
                        clearable=True,
                    ).classes("flex-1")

                expertise = ui.input(
                    "Champ d'expertise",
                    value=str(effort.get("Champs d'expertise") or ""),
                ).classes("w-full")
                precision = ui.textarea(
                    "Précision",
                    value=str(effort.get("Précision") or ""),
                ).classes("w-full")
                note = ui.textarea(
                    "Note",
                    value=str(effort.get("Note") or ""),
                ).classes("w-full")

                with ui.row().classes("w-full items-center gap-6"):
                    planned_flag = None
                    closed_flag = None
                    if "Planifié" in effort:
                        planned_flag = ui.checkbox(
                            "Planifié",
                            value=_truthy(effort.get("Planifié")),
                        )
                    if "Fermé" in effort:
                        closed_flag = ui.checkbox(
                            "Fermé",
                            value=_truthy(effort.get("Fermé")),
                        )

                def save_effort() -> None:
                    start_date = _date_from_any(start.value)
                    end_date = _date_from_any(end.value) or start_date
                    if not start_date:
                        ui.notify("La date de début est requise.", type="warning")
                        return
                    if end_date and end_date < start_date:
                        ui.notify("La date de fin ne peut pas précéder la date de début.", type="warning")
                        return
                    if v13._number(hours.value) < 0:
                        ui.notify("Les efforts prévus ne peuvent pas être négatifs.", type="warning")
                        return

                    updates: dict[str, Any] = {
                        "Date de début": start.value,
                        "Date de fin": end.value,
                        "Efforts Prévus": hours.value,
                        "Équipe/Technicien attitré": assigned.value,
                        "Compétence": competence.value,
                        "Champs d'expertise": expertise.value,
                        "Status": status.value,
                        "Précision": precision.value,
                        "Note": note.value,
                    }
                    if planned_flag is not None:
                        updates["Planifié"] = bool(planned_flag.value)
                    if closed_flag is not None:
                        updates["Fermé"] = bool(closed_flag.value)

                    try:
                        self.repo.update_effort(row, updates)
                        dialog.close()
                        self._after_write(
                            f"Planification moyen terme mise à jour — ligne {row}"
                        )
                    except Exception as exc:
                        ui.notify(str(exc), type="negative")

                with ui.row().classes("w-full justify-end"):
                    ui.button(
                        "Enregistrer la planification",
                        icon="save",
                        on_click=save_effort,
                    ).props("unelevated no-caps color=primary")

            with ui.card().classes("w-full border border-gray-200 shadow-none"):
                with ui.row().classes("w-full items-center"):
                    ui.label("Demandes MO liées").classes("font-semibold")
                    ui.space()
                    ui.label(f"{len(linked)} demande(s)").classes("text-xs muted")

                if not linked:
                    ui.label("Aucune demande MO liée à cette ligne.").classes("text-sm muted")
                else:
                    ui.label(
                        "Les demandes sont affichées ici à titre de référence; leur modification se fait dans "
                        "Demandes / approbations."
                    ).classes("text-xs muted")
                    for demand in linked:
                        with ui.row().classes("w-full items-center border-b border-gray-100 py-2"):
                            with ui.column().classes("gap-0"):
                                ui.label(str(demand.get("NoDemande") or "")).classes("font-semibold")
                                ui.label(
                                    f"{demand.get('Statut') or '—'} · "
                                    f"{demand.get('CompetencesRequises') or 'Compétence non précisée'}"
                                ).classes("text-xs muted")
                            ui.space()
                            ui.button(
                                "Segments",
                                icon="view_timeline",
                                on_click=lambda d=demand: v14._segments_from_medium_term(
                                    self, dialog, d
                                ),
                            ).props("flat dense no-caps")

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
    # La cible est remplacée après l'installation de la V1.4.
    v14._open_effort_macro_dialog_v14 = _open_effort_macro_dialog_fixed
    v13._open_effort_macro_dialog = _open_effort_macro_dialog_fixed
    ui_module.PlannerUI._v14_fixes_installed = True
