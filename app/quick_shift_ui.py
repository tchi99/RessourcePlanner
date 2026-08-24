from __future__ import annotations

from datetime import date
from typing import Any

from nicegui import ui

from . import v15_engine, v17
from .application.quick_shift_service import QuickShiftService
from .operational_planning_cell_action import (
    register_operational_planning_cell_shift_opener,
)
from .segment_repository import (
    SEGMENT_ORIGIN_FIELD,
    add_segment,
    ensure_segment_fields,
    number,
    update_segment,
)


MODE_QUICK = "quick"
MODE_SEGMENT = "segment"
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


def _quick_shift_service(repo: Any) -> QuickShiftService[Any]:
    ensure_segment_fields(repo, [SEGMENT_ORIGIN_FIELD])
    return QuickShiftService(
        repo,
        create_segment_record=lambda target_repo, values: add_segment(
            target_repo, dict(values)
        ),
        cancel_segment_record=lambda target_repo, segment_id: update_segment(
            target_repo,
            segment_id,
            {"Statut": "Annulé"},
        ),
        create_locked_shift_record=v15_engine.create_manual_allocation,
    )


def open_cell_shift_dialog(owner: Any, technician: str, day: date) -> None:
    """Open the single cell action for ad-hoc or existing-segment shifts."""
    candidates = v17._eligible_segments_for_cell(owner.repo, technician, day)
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
    project_options, project_names = _project_options(owner.repo)
    capacity, used, free = v17._day_standard_load(owner.repo, technician, day)
    suggested_quick_hours = max(min(8.0, free if free > 0 else 8.0), 0.25)

    owner.interaction_lock = True
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
                    - v17._locked_hours(owner.repo, first_segment_id),
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
                            - v17._locked_hours(owner.repo, segment_id),
                            0.25,
                        )
                        segment_hours.value = max(
                            min(8.0, lockable, free if free > 0 else 8.0),
                            0.25,
                        )
                    message, match = v17._skill_message(
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
            try:
                if str(mode.value or MODE_QUICK) == MODE_QUICK:
                    project_number = str(project_select.value or "").strip()
                    if not project_number:
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
                    )
                    dialog.close()
                    owner._after_write(
                        f"Quart rapide de {number(quick_hours.value):g} h créé pour "
                        f"{technician} · {project_number} · {result.segment_id}"
                    )
                    return

                if segment_select is None or segment_hours is None:
                    ui.notify(
                        "Aucun segment compatible n'est disponible.",
                        type="warning",
                    )
                    return
                segment_id = str(segment_select.value or "")
                if not segment_id:
                    ui.notify("Sélectionne un segment.", type="warning")
                    return
                v17._validate_locked_total(
                    owner.repo,
                    segment_id,
                    segment_hours.value,
                )
                v15_engine.create_manual_allocation(
                    owner.repo,
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
                )
                dialog.close()
                owner._after_write(
                    f"Quart de {number(segment_hours.value):g} h planifié pour {technician}"
                )
            except Exception as exc:
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
