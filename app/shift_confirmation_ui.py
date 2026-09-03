from __future__ import annotations

from datetime import date
from typing import Any

from nicegui import ui

from . import ui as ui_module
from . import v13, v14_engine, v15_engine, v15_refinements
from .domain.confirmation import (
    CONFIRMATION_CONFIRMED,
    CONFIRMATION_TENTATIVE,
    effective_confirmation,
)
from .infrastructure.excel.command_adapters import (
    ALLOCATION_CONFIRMATION_FIELD,
    _ensure_allocation_confirmation_field,
    _set_allocation_confirmation,
)
from .segment_editor_ui import open_segment_editor
from .bugfixes import schedulable_technicians
from .excel_repository import _date_from_any


INHERIT_CONFIRMATION = "__inherit__"


def allocation_confirmation(
    allocation: dict[str, Any] | None,
    demand: dict[str, Any] | None,
) -> str:
    """Resolve the effective V1 shift confirmation without duplicating inheritance."""

    return effective_confirmation(
        (allocation or {}).get(ALLOCATION_CONFIRMATION_FIELD),
        v15_refinements.demand_confirmation(demand),
        default=CONFIRMATION_CONFIRMED,
    )


def allocation_style(
    allocation: dict[str, Any],
    demand: dict[str, Any],
    overloaded: bool,
) -> tuple[str, str]:
    """Keep the V1 colors while honoring a shift-level confirmation override."""

    if v15_refinements.is_missing_allocation(allocation):
        return (
            "background:#fff7ed;border:2px dashed #f97316;opacity:.92;",
            "Hors horaire requis",
        )
    if v15_engine._truthy(allocation.get("HorsHoraire")):
        return "background:#ffedd5;border-left:4px solid #ea580c;", "Hors horaire"
    if overloaded:
        return "background:#fee2e2;border-left:4px solid #dc2626;", "Surchargé"
    if allocation_confirmation(allocation, demand) == CONFIRMATION_TENTATIVE:
        return "background:#fef3c7;border:2px dashed #d97706;", "Tentative"
    if v15_engine._truthy(allocation.get("Verrouillee")) or str(
        allocation.get("TypeAllocation") or ""
    ) == "Fixe":
        return "background:#ede9fe;border-left:4px solid #7c3aed;", "Fixe / verrouillé"
    return "background:#dbeafe;border-left:4px solid #2563eb;", "Flexible"


def open_allocation_dialog(
    self: ui_module.PlannerUI,
    allocation: dict[str, Any] | None = None,
    segment: dict[str, Any] | None = None,
    default_date: date | None = None,
) -> None:
    """Edit a V1 shift, including its nullable Tentative/Confirmée override."""

    if allocation and v15_refinements.is_missing_allocation(allocation):
        segment_id = str(allocation.get("IDSegment") or "")
        target = next(
            (
                row
                for row in v13.segment_records(self.repo, include_cancelled=False)
                if str(row.get("IDSegment") or "") == segment_id
            ),
            None,
        )
        if target:
            open_segment_editor(self, segment=target)
        return

    _ensure_allocation_confirmation_field(self.repo)
    self.interaction_lock = True
    editing = allocation is not None
    segments = [
        row
        for row in v13.segment_records(self.repo, include_cancelled=False)
        if str(row.get("Statut") or "") not in {"Annulé", "Terminé"}
    ]
    segment_lookup = {str(row.get("IDSegment") or ""): row for row in segments}
    segment_options = {
        str(row.get("IDSegment") or ""): (
            f"{row.get('IDSegment')} — {row.get('NumeroProjet') or '—'} · "
            f"{row.get('NomProjet') or ''}"
        )
        for row in segments
        if row.get("IDSegment")
    }
    initial_segment_id = str(
        (allocation or {}).get("IDSegment")
        or (segment or {}).get("IDSegment")
        or ""
    )
    initial_segment = segment_lookup.get(initial_segment_id, segment or {})
    tech_options = [row["name"] for row in schedulable_technicians(self.repo)]
    initial_tech = str(
        (allocation or {}).get("Technicien")
        or initial_segment.get("Technicien")
        or ""
    ).strip()
    if initial_tech and initial_tech not in tech_options:
        tech_options.append(initial_tech)
    initial_day = (
        _date_from_any((allocation or {}).get("Date"))
        or default_date
        or _date_from_any(initial_segment.get("DateDebut"))
        or self.current_week
    )

    demands = v14_engine.demand_lookup(self.repo)
    demand = demands.get(str(initial_segment.get("NoDemande") or ""), {})
    inherited = effective_confirmation(
        initial_segment.get("Confirmation"),
        v15_refinements.demand_confirmation(demand),
        default=CONFIRMATION_CONFIRMED,
    )
    current_override = str(
        (allocation or {}).get(ALLOCATION_CONFIRMATION_FIELD) or ""
    ).strip()
    confirmation_value = (
        current_override
        if current_override in {CONFIRMATION_TENTATIVE, CONFIRMATION_CONFIRMED}
        else INHERIT_CONFIRMATION
    )
    confirmation_options = {
        INHERIT_CONFIRMATION: f"Héritée du segment / de la demande ({inherited})",
        CONFIRMATION_TENTATIVE: CONFIRMATION_TENTATIVE,
        CONFIRMATION_CONFIRMED: CONFIRMATION_CONFIRMED,
    }

    with ui.dialog() as dialog, ui.card().classes("w-[720px] max-w-full"):
        ui.label(
            "Modifier / verrouiller le quart" if editing else "Nouveau quart manuel"
        ).classes("text-xl font-bold")
        ui.label(
            "La confirmation peut être héritée du segment/de la demande ou remplacée "
            "uniquement pour ce quart."
        ).classes("text-xs muted")

        segment_select = ui.select(
            segment_options,
            label="Segment",
            value=initial_segment_id or None,
            with_input=True,
        ).classes("w-full")
        if editing:
            segment_select.props("readonly")

        with ui.row().classes("w-full"):
            technician = ui.select(
                tech_options,
                label="Technicien",
                value=initial_tech or None,
                with_input=True,
            ).classes("flex-1")
            day = ui.input(
                "Date",
                value=initial_day.isoformat() if initial_day else "",
            ).props("type=date").classes("flex-1")
            hours = ui.number(
                "Heures",
                value=v13._number((allocation or {}).get("Heures")) or None,
                min=0.25,
                step=0.25,
            ).classes("flex-1")

        confirmation = ui.select(
            confirmation_options,
            label="Confirmation du quart",
            value=confirmation_value,
        ).classes("w-full")
        hors_horaire = ui.checkbox(
            "Autoriser explicitement ce quart hors horaire standard",
            value=v15_engine._truthy((allocation or {}).get("HorsHoraire")),
        )
        note = ui.input(
            "Note",
            value=str((allocation or {}).get("Note") or ""),
        ).classes("w-full")

        def open_segment() -> None:
            target = segment_lookup.get(str(segment_select.value or ""))
            dialog.close()
            if target:
                ui.timer(
                    0.05,
                    lambda: open_segment_editor(self, segment=target),
                    once=True,
                )

        def selected_confirmation() -> str | None:
            value = str(confirmation.value or INHERIT_CONFIRMATION)
            return None if value == INHERIT_CONFIRMATION else value

        def save() -> None:
            if not segment_select.value or not technician.value or not day.value:
                ui.notify("Segment, technicien et date sont requis.", type="warning")
                return
            try:
                chosen_confirmation = selected_confirmation()
                if editing:
                    allocation_id = str(allocation.get("IDAllocation") or "")
                    v15_engine.update_manual_allocation(
                        self.repo,
                        allocation_id,
                        str(technician.value),
                        day.value,
                        hours.value,
                        bool(hors_horaire.value),
                        str(note.value or ""),
                        chosen_confirmation,
                    )
                    if chosen_confirmation is None:
                        # ``None`` remains the backwards-compatible "argument omitted"
                        # value at the application seam. The V1 dialog is explicit:
                        # choosing inheritance must therefore clear the persisted cell.
                        _set_allocation_confirmation(self.repo, allocation_id, None)
                    message = "Quart verrouillé et mis à jour"
                else:
                    v15_engine.create_manual_allocation(
                        self.repo,
                        str(segment_select.value),
                        str(technician.value),
                        day.value,
                        hours.value,
                        bool(hors_horaire.value),
                        str(note.value or ""),
                        chosen_confirmation,
                    )
                    message = "Quart manuel créé"
                dialog.close()
                self._after_write(message)
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        def release() -> None:
            try:
                v15_engine.release_manual_allocation(
                    self.repo,
                    str(allocation.get("IDAllocation") or ""),
                )
                dialog.close()
                self._after_write("Quart remis en planification automatique")
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        def delete() -> None:
            try:
                v15_engine.delete_manual_allocation(
                    self.repo,
                    str(allocation.get("IDAllocation") or ""),
                )
                dialog.close()
                self._after_write(
                    "Quart manuel supprimé; le reliquat a été recalculé"
                )
            except Exception as exc:
                ui.notify(str(exc), type="negative")

        with ui.row().classes("w-full justify-end"):
            ui.button("Fermer", on_click=dialog.close).props("flat no-caps")
            ui.button(
                "Modifier le segment",
                icon="view_timeline",
                on_click=open_segment,
            ).props("outline no-caps")
            if editing and v15_engine._truthy(allocation.get("Verrouillee")):
                ui.button(
                    "Revenir à l'automatique",
                    icon="autorenew",
                    on_click=release,
                ).props("outline no-caps")
                ui.button(
                    "Supprimer le quart",
                    icon="delete",
                    on_click=delete,
                ).props("flat no-caps color=negative")
            ui.button(
                "Enregistrer les modifications" if editing else "Enregistrer et verrouiller",
                icon="save" if editing else "lock",
                on_click=save,
            ).props("unelevated no-caps color=primary")

    dialog.on("hide", lambda _: self._unlock())
    dialog.open()
