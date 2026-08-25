from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from nicegui import ui


@dataclass(frozen=True)
class WorkSectionsBindings:
    """Dependencies required by the extracted operational-planning work sections."""

    all_projects: str
    all_confirmations: str
    demand_confirmation: Callable[[dict[str, Any]], str]
    segment_competence: Callable[[dict[str, Any], dict[str, dict[str, Any]]], str | None]
    required_class: Callable[[Any, dict[str, Any]], str | None]
    number: Callable[[Any], float]
    make_draggable: Callable[[Any, str], Any]
    open_recommendation_dialog: Callable[[Any, dict[str, Any]], None]
    open_segment_dialog: Callable[[Any, dict[str, Any]], None]
    open_request_dialog: Callable[[Any, dict[str, Any]], None]
    date_text: Callable[[Any, Any], str]


def visible_unassigned_segments(
    unassigned: list[dict[str, Any]],
    demands: dict[str, dict[str, Any]],
    project_filter: str,
    confirmation_filter: str,
    *,
    bindings: WorkSectionsBindings,
) -> list[dict[str, Any]]:
    return [
        segment
        for segment in unassigned
        if (
            project_filter == bindings.all_projects
            or str(segment.get("NumeroProjet") or "") == project_filter
        )
        and (
            confirmation_filter == bindings.all_confirmations
            or bindings.demand_confirmation(
                demands.get(str(segment.get("NoDemande") or ""), {})
            )
            == confirmation_filter
        )
    ]


def visible_pending_demands(
    pending: list[dict[str, Any]],
    project_filter: str,
    confirmation_filter: str,
    *,
    bindings: WorkSectionsBindings,
) -> list[dict[str, Any]]:
    return [
        demand
        for demand in pending
        if (
            project_filter == bindings.all_projects
            or str(demand.get("NumeroProjet") or "") == project_filter
        )
        and (
            confirmation_filter == bindings.all_confirmations
            or bindings.demand_confirmation(demand) == confirmation_filter
        )
    ]


def render_operational_planning_work_sections(
    owner: Any,
    unassigned: list[dict[str, Any]],
    pending: list[dict[str, Any]],
    demands: dict[str, dict[str, Any]],
    project_filter: str,
    confirmation_filter: str,
    *,
    bindings: WorkSectionsBindings,
) -> None:
    """Render backlog and pending-approval cards above the resource grid."""

    visible_unassigned = visible_unassigned_segments(
        unassigned,
        demands,
        project_filter,
        confirmation_filter,
        bindings=bindings,
    )
    if visible_unassigned:
        with ui.card().classes("section-card w-full"):
            ui.label(
                f"Travaux à planifier cette semaine ({len(visible_unassigned)})"
            ).classes("text-lg font-semibold")
            ui.label(
                "Tu peux utiliser Trouver une ressource ou glisser directement une carte sur le nom d'une ressource."
            ).classes("text-xs muted")
            with ui.row().classes("w-full gap-2 flex-wrap"):
                for segment in visible_unassigned[:20]:
                    competence = (
                        bindings.segment_competence(segment, demands)
                        or "Compétence non précisée"
                    )
                    required_class = bindings.required_class(owner.repo, segment)
                    card = ui.card().classes("p-3 min-w-[280px] max-w-[370px]")
                    bindings.make_draggable(
                        card,
                        f"segment:{segment.get('IDSegment') or ''}",
                    )
                    with card:
                        ui.label(
                            f"{segment.get('NumeroProjet') or '—'} · {segment.get('NomProjet') or ''}"
                        ).classes("text-sm font-semibold")
                        ui.label(str(segment.get("Description") or "")).classes("text-xs")
                        ui.label(
                            f"{competence} · {required_class or 'Classe non déterminée'} · "
                            f"{bindings.number(segment.get('HeuresPrevues')):g} h"
                        ).classes("text-xs text-orange-700")
                        with ui.row().classes("gap-1"):
                            ui.button(
                                "Trouver une ressource",
                                icon="recommend",
                                on_click=lambda _, s=segment: bindings.open_recommendation_dialog(
                                    owner, s
                                ),
                            ).props("unelevated dense no-caps color=primary")
                            ui.button(
                                "Segment",
                                icon="view_timeline",
                                on_click=lambda _, s=segment: bindings.open_segment_dialog(
                                    owner, s
                                ),
                            ).props("flat dense no-caps")

    visible_pending = visible_pending_demands(
        pending,
        project_filter,
        confirmation_filter,
        bindings=bindings,
    )
    if visible_pending:
        with ui.card().classes("section-card w-full"):
            ui.label(
                f"En attente d'approbation dans cette semaine ({len(visible_pending)})"
            ).classes("text-lg font-semibold")
            ui.label(
                "Ces besoins comptent 0 h de charge. Clique une carte pour ouvrir la demande."
            ).classes("text-xs muted")
            with ui.row().classes("w-full gap-2 flex-wrap"):
                for demand in visible_pending[:20]:
                    tentative = bindings.demand_confirmation(demand) == "Tentative"
                    style = (
                        "background:#fffbeb;border:2px dashed #d97706;cursor:pointer;"
                        if tentative
                        else "background:#f9fafb;border:1px dashed #9ca3af;cursor:pointer;"
                    )
                    card = ui.card().classes(
                        "p-3 min-w-[250px] max-w-[340px]"
                    ).style(style)
                    card.on(
                        "click",
                        lambda _, d=demand: bindings.open_request_dialog(owner, d),
                    )
                    with card:
                        ui.label(
                            f"{demand.get('NumeroProjet') or '—'} · {demand.get('NomProjet') or ''}"
                        ).classes("text-sm font-semibold")
                        ui.label(
                            f"{bindings.demand_confirmation(demand)} · "
                            f"{demand.get('CompetencesRequises') or 'Compétence non précisée'}"
                        ).classes("text-xs")
                        ui.label(
                            f"{bindings.date_text(owner, demand.get('DateDebutSouhaitee'))} → "
                            f"{bindings.date_text(owner, demand.get('DateFinSouhaitee'))}"
                        ).classes("text-xs muted")
