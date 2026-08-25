from __future__ import annotations

from typing import Any

from nicegui import ui

from . import ui as ui_module
from . import v16, v16_refinements, v17_refinements
from .bugfixes import schedulable_technicians
from .operational_planning_page import register_operational_planning_renderer
from .operational_planning_renderer import compose_operational_planning_renderer
from .operational_planning_sorting import (
    MANUAL_ORDER_EVENT,
    SORT_MANUAL,
    alpha_key,
    manual_order_script as build_manual_order_script,
    rank_weekly_stats,
    set_resource_sort,
)


def ranked_weekly_stats(
    owner: ui_module.PlannerUI,
    original_stats: Any,
    repo: Any,
    week: Any,
) -> dict[str, dict[str, float]]:
    return rank_weekly_stats(
        owner,
        original_stats,
        repo,
        week,
        order_map=v17_refinements._resource_order_map,
    )


def manual_order_script(owner: ui_module.PlannerUI) -> str:
    technicians = [
        str(row.get("name") or "").strip()
        for row in schedulable_technicians(owner.repo)
    ]
    return build_manual_order_script(owner, technicians)


def move_manual_resource(
    owner: ui_module.PlannerUI,
    technician: str,
    direction: int,
) -> None:
    if str(getattr(owner, "planning_resource_sort", "")) != SORT_MANUAL:
        return

    name = str(technician or "").strip()
    if not name or direction not in {-1, 1}:
        return

    class_map = v16.resource_class_map(owner.repo)
    group = class_map.get(name, v16.UNCLASSIFIED)
    manual = v17_refinements._resource_order_map(owner.repo)
    profiles = v16_refinements.resource_profile_map(owner.repo)

    group_names = [
        str(row.get("name") or "").strip()
        for row in schedulable_technicians(owner.repo)
        if class_map.get(str(row.get("name") or "").strip(), v16.UNCLASSIFIED) == group
    ]
    group_names.sort(
        key=lambda item: (
            0 if item in manual else 1,
            manual.get(item, 0.0),
            alpha_key(item),
            item.casefold(),
        )
    )

    try:
        index = group_names.index(name)
    except ValueError:
        return
    target = index + direction
    if target < 0 or target >= len(group_names):
        ui.notify(
            "Cette ressource est déjà en première position."
            if direction < 0
            else "Cette ressource est déjà en dernière position.",
            type="info",
        )
        return

    group_names[index], group_names[target] = group_names[target], group_names[index]

    try:
        for position, resource_name in enumerate(group_names, start=1):
            profile = profiles.get(resource_name, {})
            resource_class = profile.get("class")
            if resource_class == v16.UNCLASSIFIED:
                resource_class = None
            v16_refinements.update_resource_profile(
                owner.repo,
                resource_name,
                resource_class,
                profile.get("competencies") or [],
                str(profile.get("note") or ""),
                position * 10,
            )
        owner._after_write(f"{name} déplacé dans l'ordre manuel")
    except Exception as exc:
        ui.notify(str(exc), type="negative")


def register_manual_order_handler(owner: ui_module.PlannerUI) -> None:
    if getattr(owner, "_operational_manual_order_handler_registered", False):
        return

    def handler(event: Any) -> None:
        args = getattr(event, "args", {}) or {}
        try:
            direction = int(args.get("direction") or 0)
        except (TypeError, ValueError):
            direction = 0
        technician = str(args.get("technician") or "")
        mover = getattr(owner, "move_resource_manual", None)
        if callable(mover):
            mover(technician, direction)
        else:
            move_manual_resource(owner, technician, direction)

    ui.on(MANUAL_ORDER_EVENT, handler)
    owner._operational_manual_order_handler_registered = True


def install_operational_planning_sorting() -> None:
    """Install the authoritative operational-planning resource sort path."""

    if getattr(ui_module.PlannerUI, "_operational_planning_sorting_installed", False):
        return

    # Preserve the V1.7.1 behavior while the base renderer still lives in
    # v17_refinements: the old DOM reorder is disabled and the selector refreshes the
    # Python-ranked renderer instead.
    v17_refinements._resource_sort_script = lambda _owner: "void 0;"
    v17_refinements._set_resource_sort = set_resource_sort

    render_planning = compose_operational_planning_renderer(
        base_render=v17_refinements._render_planning,
        weekly_stats_provider=v16._weekly_resource_stats,
        rank_weekly_stats=ranked_weekly_stats,
        register_manual_order_handler=register_manual_order_handler,
        manual_order_script=manual_order_script,
    )

    register_operational_planning_renderer(render_planning)
    ui_module.PlannerUI.move_resource_manual = move_manual_resource
    ui_module.PlannerUI._operational_planning_sorting_installed = True
