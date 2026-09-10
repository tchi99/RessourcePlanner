from __future__ import annotations

from . import features, v13, v15, v15_engine, v15_refinements, v16
from .operational_planning_drag_drop import make_draggable, make_drop_zone
from .operational_planning_resource_row import ResourceRowBindings
from .shift_confirmation_ui import (
    allocation_confirmation,
    allocation_style,
    open_allocation_dialog,
)


def _business_key(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        number = float(text.replace(",", "."))
        if number.is_integer():
            return str(int(number))
    except (TypeError, ValueError):
        pass
    return text


def _project_manager_for_project(repo, project_number: str) -> str:
    wanted = _business_key(project_number)
    if not wanted:
        return ""
    try:
        projects = repo.projects(active_only=False)
    except Exception:
        return ""
    for row in projects:
        if _business_key(row.get("Numéro de Projet")) == wanted:
            return str(row.get("Chargé de projet") or "").strip()
    return ""


def operational_planning_resource_row_bindings() -> ResourceRowBindings:
    """Compose the extracted row renderer from transitional V1.x helpers.

    This is an explicit compatibility boundary. Keeping these versioned imports here
    prevents the extracted renderer and the V1.7 renderer from owning the wiring.
    """
    return ResourceRowBindings(
        make_drop_zone=make_drop_zone,
        availability_for_day=features.availability_for_day,
        availability_hours=v13._availability_hours,
        all_projects=v16.ALL_PROJECTS,
        project_number_for_allocation=v16._project_number_for_allocation,
        all_confirmations=v16.ALL_CONFIRMATIONS,
        demand_confirmation=v15_refinements.demand_confirmation,
        allocation_confirmation=allocation_confirmation,
        is_missing_allocation=v15_refinements.is_missing_allocation,
        pending_covers_day=v15._pending_covers_day,
        number=v13._number,
        truthy=v15_engine._truthy,
        allocation_style=allocation_style,
        open_allocation_dialog=open_allocation_dialog,
        make_draggable=make_draggable,
        project_manager_for_project=_project_manager_for_project,
    )
