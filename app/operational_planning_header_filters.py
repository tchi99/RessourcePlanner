from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Sequence

from nicegui import ui


@dataclass(frozen=True)
class HeaderFilterBindings:
    """Dependencies required by the extracted planning header and filter panel."""

    all_classes: str
    resource_classes: Sequence[str]
    unclassified: str
    all_resources: str
    all_projects: str
    all_confirmations: str
    filter_value: Callable[[Any, str, Any], Any]
    set_filter: Callable[[Any, str, Any], None]
    project_labels: Callable[[Any], dict[str, str]]
    open_manual_allocation: Callable[[Any], None]
    recalculate: Callable[[Any], None]


@dataclass(frozen=True)
class PlanningFilterState:
    class_filter: Any
    resource_filter: Any
    project_filter: Any
    confirmation_filter: Any
    only_available: bool
    project_options: dict[str, str]


def resolve_planning_filter_state(
    owner: Any,
    allocations: list[dict[str, Any]],
    unassigned: list[dict[str, Any]],
    pending: list[dict[str, Any]],
    *,
    bindings: HeaderFilterBindings,
) -> PlanningFilterState:
    """Resolve persisted filter values and project options for one planning render."""

    class_filter = bindings.filter_value(
        owner,
        "planning_class_filter",
        bindings.all_classes,
    )
    resource_filter = bindings.filter_value(
        owner,
        "planning_resource_filter",
        bindings.all_resources,
    )
    project_filter = bindings.filter_value(
        owner,
        "planning_project_filter",
        bindings.all_projects,
    )
    confirmation_filter = bindings.filter_value(
        owner,
        "planning_confirmation_filter",
        bindings.all_confirmations,
    )
    only_available = bool(
        bindings.filter_value(owner, "planning_only_available", False)
    )

    project_values = sorted(
        {
            str(row.get("NumeroProjet") or "").strip()
            for row in [*allocations, *unassigned, *pending]
            if str(row.get("NumeroProjet") or "").strip()
        }
    )
    labels = bindings.project_labels(owner.repo)
    project_options = {bindings.all_projects: bindings.all_projects}
    for number in project_values:
        project_options[number] = labels.get(number, number)

    return PlanningFilterState(
        class_filter=class_filter,
        resource_filter=resource_filter,
        project_filter=project_filter,
        confirmation_filter=confirmation_filter,
        only_available=only_available,
        project_options=project_options,
    )


def render_operational_planning_header_filters(
    owner: Any,
    days: list[date],
    techs: list[dict[str, Any]],
    state: PlanningFilterState,
    *,
    bindings: HeaderFilterBindings,
) -> None:
    """Render the operational-planning title, navigation and filter controls."""

    with ui.row().classes("w-full items-center"):
        with ui.column().classes("gap-0"):
            ui.label("Planning opérationnel").classes("text-2xl font-bold")
            ui.label(
                "Glisser un quart sur une autre journée pour le verrouiller; glisser sur une autre ressource permet de réaffecter ou fractionner."
            ).classes("muted")
        ui.space()
        ui.button(
            "Quart manuel",
            icon="add_task",
            on_click=lambda: bindings.open_manual_allocation(owner),
        ).props("outline no-caps")
        ui.button(
            "Recalculer",
            icon="calculate",
            on_click=lambda: bindings.recalculate(owner),
        ).props("outline no-caps")
        ui.button(icon="chevron_left", on_click=owner.previous_week).props("flat round")
        ui.button("Aujourd'hui", on_click=owner.today_week).props("outline no-caps")
        ui.button(icon="chevron_right", on_click=owner.next_week).props("flat round")
        ui.label(
            f"{days[0].strftime('%d %b')} – {days[-1].strftime('%d %b %Y')}"
        ).classes("font-semibold ml-2")

    with ui.card().classes("section-card w-full"):
        with ui.row().classes("w-full items-end gap-3"):
            ui.select(
                [bindings.all_classes, *bindings.resource_classes, bindings.unclassified],
                label="Classe",
                value=state.class_filter,
                on_change=lambda event: bindings.set_filter(
                    owner,
                    "planning_class_filter",
                    event.value,
                ),
            ).classes("min-w-[190px]")
            ui.select(
                [bindings.all_resources, *sorted(tech["name"] for tech in techs)],
                label="Ressource",
                value=state.resource_filter,
                with_input=True,
                on_change=lambda event: bindings.set_filter(
                    owner,
                    "planning_resource_filter",
                    event.value,
                ),
            ).classes("min-w-[210px]")
            ui.select(
                state.project_options,
                label="Projet",
                value=state.project_filter,
                with_input=True,
                on_change=lambda event: bindings.set_filter(
                    owner,
                    "planning_project_filter",
                    event.value,
                ),
            ).classes("min-w-[250px]")
            ui.select(
                [bindings.all_confirmations, "Confirmée", "Tentative"],
                label="Confirmation",
                value=state.confirmation_filter,
                on_change=lambda event: bindings.set_filter(
                    owner,
                    "planning_confirmation_filter",
                    event.value,
                ),
            ).classes("min-w-[160px]")
            ui.checkbox(
                "Seulement avec capacité",
                value=state.only_available,
                on_change=lambda event: bindings.set_filter(
                    owner,
                    "planning_only_available",
                    event.value,
                ),
            )
