from __future__ import annotations

from datetime import date, timedelta
from threading import RLock
from typing import Any

from nicegui import ui

from . import v13, v16, v18
from .bugfixes import schedulable_technicians
from .domain.capacity_projection import projected_hours_in_window
from .excel_repository import _date_from_any


_RENDER_LOCK = RLock()


def _effort_class(
    effort: dict[str, Any],
    class_map: dict[str, str],
    linked_segments: list[dict[str, Any]],
) -> str:
    technician = str(effort.get("Équipe/Technicien attitré") or "").strip()
    if technician:
        return class_map.get(technician, v16.UNCLASSIFIED)

    linked_classes = {
        class_map.get(str(row.get("Technicien") or "").strip(), v16.UNCLASSIFIED)
        for row in linked_segments
        if str(row.get("Technicien") or "").strip()
    }
    if len(linked_classes) == 1:
        return next(iter(linked_classes))
    return v16.UNCLASSIFIED


def _style_for_load(capacity: float, planned: float, projected: float) -> str:
    exposure = max(planned, projected)
    if capacity <= 0:
        if exposure > 0:
            return "background:#fee2e2;color:#991b1b;"
        return "background:#f3f4f6;color:#6b7280;"
    pct = exposure / capacity * 100
    if pct > 100:
        return "background:#fee2e2;color:#991b1b;"
    if pct >= 85:
        return "background:#fef3c7;color:#92400e;"
    return "background:#dcfce7;color:#166534;"


def render_capacity_heatmap_with_projection(
    owner: Any,
    weeks: list[date],
    class_map: dict[str, str],
    selected_classes: set[str],
) -> None:
    """Render current operational load beside macro WorkPackage projection.

    Planned and projected values are deliberately separate. The macro forecast never gets
    added to allocated hours, so converting a medium-term envelope into detailed planning
    cannot inflate the capacity signal through double counting.
    """

    if not weeks:
        return
    window_start = weeks[0]
    window_end = weeks[-1] + timedelta(days=6)
    tech_rows = schedulable_technicians(owner.repo, window_start, window_end)
    techs = [str(row.get("name") or "").strip() for row in tech_rows if row.get("name")]
    allocations = v16._actual_allocations(owner.repo)
    efforts = [
        effort
        for effort in owner.repo.efforts(include_closed=False)
        if v18._overlap(
            _date_from_any(effort.get("Date de début")),
            _date_from_any(effort.get("Date de fin")),
            window_start,
            window_end,
        )
    ]
    segments = v13.segment_records(owner.repo, include_cancelled=False)
    demands = {
        str(row.get("NoDemande") or ""): row
        for row in owner.repo.demands()
        if row.get("NoDemande")
    }
    linked_by_effort: dict[str, list[dict[str, Any]]] = {}
    projected_class_by_effort: dict[str, str] = {}
    for effort in efforts:
        identifier = str(effort.get(v18.EFFORT_ID_FIELD) or "").strip()
        linked = v18._linked_segments(owner.repo, effort, segments, demands)
        linked_by_effort[identifier] = linked
        projected_class_by_effort[identifier] = _effort_class(effort, class_map, linked)

    classes = list(v16.RESOURCE_CLASSES)
    has_unclassified = any(
        class_map.get(name, v16.UNCLASSIFIED) == v16.UNCLASSIFIED for name in techs
    ) or any(value == v16.UNCLASSIFIED for value in projected_class_by_effort.values())
    if has_unclassified:
        classes.append(v16.UNCLASSIFIED)
    if selected_classes:
        classes = [item for item in classes if item in selected_classes]

    with ui.expansion("Capacité par classe", icon="monitoring", value=True).classes(
        "w-full section-card"
    ):
        ui.label(
            "P = charge planifiée dans les quarts; M = charge macro projetée depuis les plages "
            "moyen terme. Les deux valeurs sont comparées séparément à la capacité standard et "
            "ne sont jamais additionnées."
        ).classes("text-xs muted mb-2")

        with ui.element("div").classes("v18-capacity-scroll"):
            with ui.element("div").classes("v18-capacity-grid"):
                ui.label("Classe").classes("v18-sticky v18-capacity-label font-semibold")
                for week in weeks:
                    ui.label(week.strftime("%d/%m")).classes(
                        "text-[10px] text-center font-semibold py-1"
                    )

                for class_name in classes:
                    names = [
                        name
                        for name in techs
                        if class_map.get(name, v16.UNCLASSIFIED) == class_name
                    ]
                    ui.label(class_name).classes(
                        "v18-sticky v18-capacity-label text-xs font-medium"
                    )
                    for week in weeks:
                        week_end = week + timedelta(days=6)
                        capacity = 0.0
                        planned = 0.0
                        projected = 0.0

                        for name in names:
                            cursor = week
                            while cursor <= week_end:
                                capacity += v13._availability_hours(owner.repo, name, cursor)
                                cursor += timedelta(days=1)

                        for allocation in allocations:
                            day = _date_from_any(allocation.get("Date"))
                            if (
                                day
                                and week <= day <= week_end
                                and str(allocation.get("Technicien") or "").strip() in names
                            ):
                                planned += v13._number(allocation.get("Heures"))

                        for effort in efforts:
                            identifier = str(effort.get(v18.EFFORT_ID_FIELD) or "").strip()
                            if projected_class_by_effort.get(identifier) != class_name:
                                continue
                            projected += projected_hours_in_window(
                                v13._number(effort.get("Efforts Prévus")),
                                _date_from_any(effort.get("Date de début")),
                                _date_from_any(effort.get("Date de fin")),
                                week,
                                week_end,
                            )

                        style = _style_for_load(capacity, planned, projected)
                        text = f"P {planned:.0f}h\nM {projected:.0f}h"
                        ui.label(text).classes(
                            "text-[9px] leading-tight text-center rounded py-1 mx-[1px] whitespace-pre-line"
                        ).style(style).tooltip(
                            f"{class_name} · semaine du {week.strftime('%d/%m/%Y')} · "
                            f"planifiée {planned:.1f} h · projetée {projected:.1f} h · "
                            f"capacité {capacity:.1f} h"
                        )


def render_medium_term_with_projected_capacity(owner: Any) -> None:
    """Scoped V1 compatibility wrapper around the existing refined renderer.

    The temporary replacement is protected and restored immediately. This keeps the
    transitional NiceGUI change localized while the durable React/FastAPI read model is
    developed independently.
    """

    from . import v18_refinements

    with _RENDER_LOCK:
        previous = v18_refinements._render_capacity_heatmap_multi
        v18_refinements._render_capacity_heatmap_multi = render_capacity_heatmap_with_projection
        try:
            v18_refinements._render_medium_term_refined(owner)
        finally:
            v18_refinements._render_capacity_heatmap_multi = previous
