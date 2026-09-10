from __future__ import annotations

from datetime import date
from typing import Any

from nicegui import ui

from .application.allocation_service import AllocationService
from .application.quick_shift_service import QuickShiftService
from .domain.confirmation import (
    CONFIRMATION_CONFIRMED,
    CONFIRMATION_TENTATIVE,
    effective_confirmation,
)
from .infrastructure.excel import ExcelSegmentRepository, excel_allocation_commands
from .operational_planning_cell_action import (
    register_operational_planning_cell_shift_opener,
)
from .operational_planning_cell_context_compat import operational_planning_cell_context
from .segment_repository import SEGMENT_ORIGIN_FIELD, ensure_segment_fields, number
from .ui_mutation_guard import MutationGate


MODE_QUICK = "quick"
MODE_SEGMENT = "segment"
SEGMENT_CONFIRMATION_FIELD = "Confirmation"
INHERIT_CONFIRMATION = "__inherit__"
_installed = False


def _normalize_project_number(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        number_value = float(text.replace(",", "."))
        if number_value.is_integer():
            return str(int(number_value))
    except (TypeError, ValueError):
        pass
    return text


def _project_options(repo: Any) -> tuple[dict[str, str], dict[str, str]]:
    try:
        rows = repo.projects(active_only=True)
        if not rows:
            rows = repo.projects(active_only=False)
    except Exception:
        rows = []

    options: dict[str, str] = {}
    names: dict[str, str] = {}
    for row in rows:
        project_number = _normalize_project_number(row.get("Numéro de Projet"))
        if not project_number:
            continue
        project_name = str(
            row.get("Nom de référence")
            or row.get("Description de l'appel d'offre")
            or ""
        ).strip()
        options[project_number] = (
            f"{project_number} — {project_name}" if project_name else project_number
        )
        names[project_number] = project_name
    return options, names


def _allocation_service(repo: Any) -> AllocationService:
    return AllocationService(excel_allocation_commands(repo))


def _quick_shift_service(repo: Any) -> QuickShiftService:
    ensure_segment_fields(repo, [SEGMENT_ORIGIN_FIELD, SEGMENT_CONFIRMATION_FIELD])
    return QuickShiftService(
        ExcelSegmentRepository(repo),
        excel_allocation_commands(repo),
    )


def open_cell_shift_dialog(owner: Any, technician: str, day: date) -> None:
    """Open the single cell action for ad-hoc or existing-segment shifts."""
    cell_context = operational_planning_cell_context()
    candidates = cell_context.eligible_segments_for_cell(owner.repo, technician, day)
    segment_lookup = {
        str(row.get("IDSegment") or ""): row
        for row in candidates
        if row.get("IDSegment")
    }
    segment_options = {
        identifier: (
            f"{identifier} — {row.get('NumeroProjet') or '—'} · "
            f"{row.get('NomProjet') or ''} · {number(row.get('HeuresPrevues')):g} h"
        )
        for identifier, row in segment_lookup.items()
    }
    demands = {
        str(row.get("NoDemande") or ""): row
        for row in owner.repo.demands()
        if row.get("NoDemande")
    }
    project_options, project_names = _project_options(owner.repo)
    capacity, used, free = cell_context.day_standard_load(
        owner.repo,
        technician,
        day,
    )
    suggested_quick_hours = max(min(8.0, free if free > 0 else 8.0), 0.25)

    owner.interaction_lock = True
    mutation_gate = MutationGate()
    with ui.dialog() as dialog, ui.card().classes("w-[780px] max-w-full"):
        ui.label("Planifier un quart").classes("text-xl font-bold")
        ui.label(f"{technician} · {day.strftime('%d/%m/%Y')}").classes(
            "font-semibold"
        )
        ui.label(
            f"Capacité standard : {capacity:g} h · déjà utilisée : {used:g} h · "
            f"libre : {free:g} h"
        ).classes("text-sm muted")

        mode = ui.toggle(
            {MODE_QUICK: "Quart rapide", MODE_SEGMENT: "Segment existant"},
            value=MODE_QUICK,
        ).props("unelevated no-caps")

        quick_panel = ui.column().classes("w-full gap-3")
        with quick_panel:
            if project_options:
                filtered_project = _normalize_project_number(
                    getattr(owner, "planning_project_filter", "")
                )
                selected_project = (
                    filtered_project
                    if filtered_project in project_options
                    else next(iter(project_options))
                )
                project_select = ui.select(
                    project_options,
                    label="Projet",
                    value=selected_project,
                    with_input=True,
                ).classes("w-full")
            else:
                project_select = ui.select(
                    {},
                    label="Projet",
                    value=None,
                ).classes("w-full")
                project_select.props("disable")
                ui.label(
                    "Aucun projet n'est disponible dans la liste des projets."
                ).classes("text-sm text-amber-700")

            quick_hours = ui.number(
                "Heures",
                value=suggested_quick_hours,
                min=0.25,
                step=0.25,
            ).classes("w-full")
            quick_confirmation = ui.select(
                [CONFIRMATION_TENTATIVE, CONFIRMATION_CONFIRMED],
                label="Confirmation du quart rapide",
                value=CONFIRMATION_CONFIRMED,
            ).classes("w-full")
            quick_description = ui.input(
                "Description",
                value="Quart rapide",
            ).classes("w-full")
            quick_overtime = ui.checkbox(
                "Hors horaire standard",
                value=capacity <= 0,
            )
            quick_note = ui.input(
                "Note",
                value="Créé rapidement depuis le planning opérationnel",
            ).classes("w-full")

        segment_panel = ui.column().classes("w-full gap-3")
        with segment_panel:
            if segment_options:
                first_segment_id = next(iter(segment_options))
                segment_select = ui.select(
                    segment_options,
                    label="Segment",
                    value=first_segment_id,
                    with_input=True,
                ).classes("w-full")
                first_segment = segment_lookup[first_segment_id]
                initial_lockable = max(
                    number(first_segment.get("HeuresPrevues"))
                    - cell_context.locked_hours(owner.repo, first_segment_id),
                    0.25,
                )
                segment_hours = ui.number(
                    "Heures",
                    value=max(
                        min(8.0, initial_lockable, free if free > 0 else 8.0),
                        0.25,
                    ),
                    min=0.25,
                    step=0.25,
                ).classes("w-full")
                segment_confirmation = ui.select(
                    {
                        INHERIT_CONFIRMATION: "Héritée du segment / de la demande",
                        CONFIRMATION_TENTATIVE: CONFIRMATION_TENTATIVE,
                        CONFIRMATION_CONFIRMED: CONFIRMATION_CONFIRMED,
                    },
                    label="Confirmation du quart",
                    value=INHERIT_CONFIRMATION,
                ).classes("w-full")
                confirmation_hint = ui.label().classes("text-xs muted")
                segment_overtime = ui.checkbox(
                    "Hors horaire standard",
                    value=capacity <= 0,
                )
                skill_label = ui.label().classes("text-xs")
                segment_note = ui.input(
                    "Note",
                    value="Planifié rapidement depuis la grille",
                ).classes("w-full")

                def refresh_segment(*_: Any) -> None:
                    segment_id = str(segment_select.value or "")
                    segment = segment_lookup.get(segment_id, {})
                    if segment_id:
                        lockable = max(
                            number(segment.get("HeuresPrevues"))
                            - cell_context.locked_hours(owner.repo, segment_id),
                            0.25,
                        )
                        segment_hours.value = max(
                            min(8.0, lockable, free if free > 0 else 8.0),
                            0.25,
                        )
                    demand = demands.get(str(segment.get("NoDemande") or ""), {})
                    inherited_confirmation = effective_confirmation(
                        segment.get(SEGMENT_CONFIRMATION_FIELD),
                        demand.get(SEGMENT_CONFIRMATION_FIELD),
                        default=CONFIRMATION_CONFIRMED,
                    )
                    confirmation_hint.text = (
                        f"Confirmation héritée actuelle : {inherited_confirmation}"
                    )
                    message, match = cell_context.skill_message(
                        owner.repo,
                        technician,
                        segment,
                    )
                    skill_label.text = message
                    skill_label.classes(
                        remove="text-green-700 text-amber-700",
                        add="text-green-700" if match else "text-amber-700",
                    )

                segment_select.on("update:model-value", refresh_segment)
                refresh_segment()
            else:
                segment_select = None
                segment_hours = None
                segment_confirmation = None
                segment_overtime = None
                segment_note = None
                ui.label(
                    "Aucun segment compatible ne couvre cette ressource et cette date. "
                    "Le mode Quart rapide reste disponible."
                ).classes("text-sm text-amber-700")

        def refresh_mode(*_: Any) -> None:
            quick = str(mode.value or MODE_QUICK) == MODE_QUICK
            quick_panel.set_visibility(quick)
            segment_panel.set_visibility(not quick)

        mode.on("update:model-value", refresh_mode)
        refresh_mode()

        def save() -> None:
            if not mutation_gate.begin():
                return
            try:
                if str(mode.value or MODE_QUICK) == MODE_QUICK:
                    project_number = str(project_select.value or "").strip()
                    if not project_number:
                        mutation_gate.retry()
                        ui.notify("Sélectionne un projet.", type="warning")
                        return
                    result = _quick_shift_service(owner.repo).create(
                        project_number=project_number,
                        project_name=project_names.get(project_number, ""),
                        technician=technician,
                        day_value=day,
                        hours_value=quick_hours.value,
                        hors_horaire=bool(quick_overtime.value),
                        note=str(quick_note.value or ""),
                        description=str(quick_description.value or ""),
                        confirmation=str(
                            quick_confirmation.value or CONFIRMATION_CONFIRMED
                        ),
                    )
                    mutation_gate.succeed()
                    dialog.close()
                    owner._after_write(
                        f"Quart rapide de {number(quick_hours.value):g} h créé pour "
                        f"{technician} · {project_number} · {result.segment_id}"
                    )
                    return

                if segment_select is None or segment_hours is None:
                    mutation_gate.retry()
                    ui.notify(
                        "Aucun segment compatible n'est disponible.",
                        type="warning",
                    )
                    return
                segment_id = str(segment_select.value or "")
                if not segment_id:
                    mutation_gate.retry()
                    ui.notify("Sélectionne un segment.", type="warning")
                    return
                cell_context.validate_locked_total(
                    owner.repo,
                    segment_id,
                    segment_hours.value,
                )
                confirmation_override = None
                if segment_confirmation is not None:
                    selected_confirmation = str(
                        segment_confirmation.value or INHERIT_CONFIRMATION
                    )
                    if selected_confirmation != INHERIT_CONFIRMATION:
                        confirmation_override = selected_confirmation
                _allocation_service(owner.repo).create_manual(
                    segment_id,
                    technician,
                    day,
                    segment_hours.value,
                    bool(segment_overtime.value)
                    if segment_overtime is not None
                    else False,
                    str(segment_note.value or "")
                    if segment_note is not None
                    else "",
                    confirmation_override,
                )
                mutation_gate.succeed()
                dialog.close()
                owner._after_write(
                    f"Quart de {number(segment_hours.value):g} h planifié pour {technician}"
                )
            except Exception as exc:
                mutation_gate.retry()
                ui.notify(str(exc), type="negative")

        with ui.row().classes("w-full justify-end"):
            ui.button("Annuler", on_click=dialog.close).props("flat no-caps")
            ui.button("Enregistrer", icon="save", on_click=save).props(
                "unelevated no-caps color=primary"
            )

    dialog.on("hide", lambda _: owner._unlock())
    dialog.open()


def install_quick_shift_ui() -> None:
    """Register the planning-cell action without rewriting a V1.x module."""
    global _installed
    if _installed:
        return

    register_operational_planning_cell_shift_opener(open_cell_shift_dialog)
    _installed = True
