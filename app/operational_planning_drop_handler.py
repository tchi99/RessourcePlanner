from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from nicegui import ui

from .operational_planning_drag_drop import DROP_EVENT


@dataclass(frozen=True)
class DropHandlerBindings:
    """Dependencies required by the extracted operational-planning drop workflow."""

    parse_date: Callable[[Any], date | None]
    segment_by_id: Callable[[Any, str], dict[str, Any] | None]
    segment_dates: Callable[[dict[str, Any]], tuple[date | None, date | None]]
    availability_hours: Callable[[Any, str, date], float]
    availability_for_day: Callable[[Any, str, date], dict[str, Any]]
    number: Callable[[Any], float]
    truthy: Callable[[Any], bool]
    update_manual_allocation: Callable[..., None]
    delete_manual_allocation: Callable[[Any, str], None]
    update_segment: Callable[[Any, str, dict[str, Any]], Any]
    add_segment: Callable[[Any, dict[str, Any]], str]
    create_manual_allocation: Callable[..., str]
    segment_overtime_field: str
    rebuild_allocations: Callable[[Any], dict[str, Any]]
    allocation_by_id: Callable[[Any, str], dict[str, Any] | None]
    is_missing_allocation: Callable[[dict[str, Any]], bool]
    skill_message: Callable[[Any, str, dict[str, Any]], tuple[str, bool]]


def _split_allocation(
    owner: Any,
    allocation: dict[str, Any],
    target_technician: str,
    target_day: date,
    hors_horaire: bool,
    *,
    bindings: DropHandlerBindings,
) -> None:
    segment_id = str(allocation.get("IDSegment") or "")
    segment = bindings.segment_by_id(owner.repo, segment_id)
    if not segment:
        raise KeyError(f"Segment {segment_id} introuvable")

    amount = bindings.number(allocation.get("Heures"))
    planned = bindings.number(segment.get("HeuresPrevues"))
    if amount <= 0:
        raise ValueError("Le quart à fractionner ne contient aucune heure.")
    if amount >= planned - 0.01:
        bindings.update_manual_allocation(
            owner.repo,
            str(allocation.get("IDAllocation") or ""),
            target_technician,
            target_day,
            amount,
            hors_horaire,
            "Segment réaffecté depuis le Planning opérationnel",
        )
        return

    if bindings.truthy(allocation.get("Verrouillee")):
        bindings.delete_manual_allocation(
            owner.repo,
            str(allocation.get("IDAllocation") or ""),
        )

    bindings.update_segment(
        owner.repo,
        segment_id,
        {"HeuresPrevues": round(planned - amount, 2)},
    )
    new_id = bindings.add_segment(
        owner.repo,
        {
            "NoDemande": segment.get("NoDemande"),
            "NumeroProjet": segment.get("NumeroProjet"),
            "NomProjet": segment.get("NomProjet"),
            "Technicien": target_technician,
            "DateDebut": segment.get("DateDebut"),
            "DateFin": segment.get("DateFin"),
            "HeuresPrevues": amount,
            "Statut": "Planifié",
            "Description": (
                f"{segment.get('Description') or ''} — fractionné depuis {segment_id}"
            ).strip(" —"),
            "SourceEffortRow": segment.get("SourceEffortRow"),
            "CompetenceRequise": segment.get("CompetenceRequise"),
            "TypePlanification": segment.get("TypePlanification") or "Flexible",
            "Priorite": segment.get("Priorite") or "Normale",
            bindings.segment_overtime_field: segment.get(bindings.segment_overtime_field)
            or "Non",
        },
    )
    bindings.create_manual_allocation(
        owner.repo,
        new_id,
        target_technician,
        target_day,
        amount,
        hors_horaire,
        f"Quart fractionné depuis {segment_id}",
    )


def _open_move_confirmation(
    owner: Any,
    allocation: dict[str, Any],
    technician: str,
    target_day: date,
    *,
    bindings: DropHandlerBindings,
) -> None:
    owner.interaction_lock = True
    state = bindings.availability_for_day(owner.repo, technician, target_day)
    with ui.dialog() as dialog, ui.card().classes("w-[620px] max-w-full"):
        ui.label("Confirmer le déplacement hors horaire").classes("text-xl font-bold")
        ui.label(
            f"{technician} · {target_day.strftime('%d/%m/%Y')} · "
            f"{bindings.number(allocation.get('Heures')):g} h"
        ).classes("font-semibold")
        ui.label(
            f"Disponibilité : {state.get('reason') or 'hors horaire standard'}."
        ).classes("text-sm text-orange-700")
        overtime = ui.checkbox("Confirmer comme quart hors horaire", value=True)

        def confirm() -> None:
            try:
                bindings.update_manual_allocation(
                    owner.repo,
                    str(allocation.get("IDAllocation") or ""),
                    technician,
                    target_day,
                    allocation.get("Heures"),
                    bool(overtime.value),
                    "Déplacé manuellement depuis le Planning opérationnel",
                )
                dialog.close()
                owner._after_write("Quart déplacé et verrouillé")
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        with ui.row().classes("w-full justify-end"):
            ui.button("Annuler", on_click=dialog.close).props("flat no-caps")
            ui.button("Confirmer", icon="check", on_click=confirm).props(
                "unelevated no-caps color=primary"
            )
    dialog.on("hide", lambda _: owner._unlock())
    dialog.open()


def _move_allocation_same_resource(
    owner: Any,
    allocation: dict[str, Any],
    technician: str,
    target_day: date,
    *,
    bindings: DropHandlerBindings,
) -> None:
    segment = bindings.segment_by_id(owner.repo, str(allocation.get("IDSegment") or ""))
    if not segment:
        ui.notify("Segment parent introuvable.", type="negative")
        return
    start, end = bindings.segment_dates(segment)
    if (start and target_day < start) or (end and target_day > end):
        ui.notify(
            "La journée cible est hors de la fenêtre du segment. Modifie d'abord les dates du segment.",
            type="warning",
        )
        return

    capacity = bindings.availability_hours(owner.repo, technician, target_day)
    if capacity <= 0:
        _open_move_confirmation(
            owner,
            allocation,
            technician,
            target_day,
            bindings=bindings,
        )
        return

    try:
        bindings.update_manual_allocation(
            owner.repo,
            str(allocation.get("IDAllocation") or ""),
            technician,
            target_day,
            allocation.get("Heures"),
            False,
            "Déplacé et verrouillé depuis le Planning opérationnel",
        )
        owner._after_write(
            f"Quart déplacé au {target_day.strftime('%d/%m/%Y')} et verrouillé"
        )
    except Exception as exc:
        ui.notify(str(exc), type="negative")


def _open_cross_resource_dialog(
    owner: Any,
    allocation: dict[str, Any],
    target_technician: str,
    target_day: date,
    *,
    bindings: DropHandlerBindings,
) -> None:
    segment = bindings.segment_by_id(owner.repo, str(allocation.get("IDSegment") or ""))
    if not segment:
        ui.notify("Segment parent introuvable.", type="negative")
        return
    start, end = bindings.segment_dates(segment)
    if (start and target_day < start) or (end and target_day > end):
        ui.notify(
            "La journée cible est hors de la fenêtre du segment. Modifie d'abord le segment.",
            type="warning",
        )
        return

    owner.interaction_lock = True
    amount = bindings.number(allocation.get("Heures"))
    planned = bindings.number(segment.get("HeuresPrevues"))
    capacity = bindings.availability_hours(owner.repo, target_technician, target_day)
    skill_message, skill_match = bindings.skill_message(
        owner.repo,
        target_technician,
        segment,
    )

    with ui.dialog() as dialog, ui.card().classes("w-[720px] max-w-full"):
        ui.label("Déplacer vers une autre ressource").classes("text-xl font-bold")
        ui.label(
            f"{segment.get('NumeroProjet') or '—'} · {amount:g} h → "
            f"{target_technician} · {target_day.strftime('%d/%m/%Y')}"
        ).classes("font-semibold")
        ui.label(skill_message).classes(
            "text-sm text-green-700" if skill_match else "text-sm text-amber-700"
        )
        ui.label(
            "Réaffecter le segment déplace aussi tout son reliquat automatique. "
            "Fractionner crée un nouveau segment uniquement pour les heures de ce quart."
        ).classes("text-sm muted")
        overtime = ui.checkbox(
            "Hors horaire standard",
            value=capacity <= 0,
        )

        def reassign() -> None:
            try:
                bindings.update_manual_allocation(
                    owner.repo,
                    str(allocation.get("IDAllocation") or ""),
                    target_technician,
                    target_day,
                    amount,
                    bool(overtime.value),
                    "Segment réaffecté par glisser-déposer",
                )
                dialog.close()
                owner._after_write(
                    f"Segment réaffecté à {target_technician}; quart verrouillé"
                )
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        def split() -> None:
            try:
                _split_allocation(
                    owner,
                    allocation,
                    target_technician,
                    target_day,
                    bool(overtime.value),
                    bindings=bindings,
                )
                dialog.close()
                owner._after_write(
                    f"{amount:g} h fractionnées vers {target_technician}"
                )
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        with ui.row().classes("w-full justify-end"):
            ui.button("Annuler", on_click=dialog.close).props("flat no-caps")
            if planned > amount + 0.01:
                ui.button("Fractionner ce quart", icon="call_split", on_click=split).props(
                    "outline no-caps"
                )
            ui.button("Réaffecter le segment", icon="person_add", on_click=reassign).props(
                "unelevated no-caps color=primary"
            )

    dialog.on("hide", lambda _: owner._unlock())
    dialog.open()


def _assign_backlog_segment(
    owner: Any,
    segment_id: str,
    technician: str,
    target_day: date | None,
    *,
    bindings: DropHandlerBindings,
) -> None:
    segment = bindings.segment_by_id(owner.repo, segment_id)
    if not segment:
        ui.notify(f"Segment {segment_id} introuvable.", type="negative")
        return
    if target_day:
        start, end = bindings.segment_dates(segment)
        if (start and target_day < start) or (end and target_day > end):
            ui.notify(
                "Le segment ne couvre pas cette journée. Dépose-le sur une ressource ou dans sa fenêtre de dates.",
                type="warning",
            )
            return
    try:
        bindings.update_segment(
            owner.repo,
            segment_id,
            {"Technicien": technician, "Statut": "Planifié"},
        )
        summary = bindings.rebuild_allocations(owner.repo)
        message = f"{segment_id} assigné à {technician}"
        if summary.get("unallocated_hours", 0) > 0:
            message += f" · {summary['unallocated_hours']:g} h à confirmer hors horaire"
        owner._after_write(message)
    except Exception as exc:
        ui.notify(str(exc), type="negative")


def handle_operational_planning_drop(
    owner: Any,
    event: Any,
    *,
    bindings: DropHandlerBindings,
) -> None:
    args = getattr(event, "args", {}) or {}
    payload = str(args.get("payload") or "")
    technician = str(args.get("technician") or "").strip()
    target_day = bindings.parse_date(args.get("date"))
    if not payload or not technician:
        return

    if payload.startswith("segment:"):
        _assign_backlog_segment(
            owner,
            payload.split(":", 1)[1],
            technician,
            target_day,
            bindings=bindings,
        )
        return

    if not payload.startswith("allocation:"):
        return
    allocation_id = payload.split(":", 1)[1]
    allocation = bindings.allocation_by_id(owner.repo, allocation_id)
    if not allocation or bindings.is_missing_allocation(allocation):
        return

    source_technician = str(allocation.get("Technicien") or "").strip()
    if target_day is None:
        if source_technician == technician:
            return
        segment = bindings.segment_by_id(
            owner.repo,
            str(allocation.get("IDSegment") or ""),
        )
        if segment:
            try:
                bindings.update_segment(
                    owner.repo,
                    str(segment.get("IDSegment") or ""),
                    {"Technicien": technician, "Statut": "Planifié"},
                )
                bindings.rebuild_allocations(owner.repo)
                owner._after_write(f"Segment réaffecté à {technician}")
            except Exception as exc:
                ui.notify(str(exc), type="negative")
        return

    if source_technician == technician:
        _move_allocation_same_resource(
            owner,
            allocation,
            technician,
            target_day,
            bindings=bindings,
        )
    else:
        _open_cross_resource_dialog(
            owner,
            allocation,
            technician,
            target_day,
            bindings=bindings,
        )


def register_operational_planning_drop_handler(
    owner: Any,
    *,
    bindings: DropHandlerBindings,
) -> None:
    """Register the shared planning drop event exactly once for one UI owner."""
    if getattr(owner, "_operational_planning_drop_handler_registered", False):
        return
    ui.on(
        DROP_EVENT,
        lambda event: handle_operational_planning_drop(owner, event, bindings=bindings),
    )
    owner._operational_planning_drop_handler_registered = True
