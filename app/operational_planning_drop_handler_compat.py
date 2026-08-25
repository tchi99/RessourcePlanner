from __future__ import annotations

from typing import Any

from . import features, v13, v15_engine, v15_refinements, v16, v16_refinements
from .excel_repository import _date_from_any
from .operational_planning_drop_handler import DropHandlerBindings


def _segment_by_id(repo: Any, segment_id: str) -> dict[str, Any] | None:
    return next(
        (
            row
            for row in v13.segment_records(repo, include_cancelled=False)
            if str(row.get("IDSegment") or "") == str(segment_id)
        ),
        None,
    )


def _skill_message(repo: Any, technician: str, segment: dict[str, Any]) -> tuple[str, bool]:
    required = str(segment.get("CompetenceRequise") or "").strip()
    if not required:
        return "Aucune compétence requise spécifiée.", True
    profile_skills = v16_refinements.resource_competence_map(repo).get(technician, set())
    match = v16._normalized_text(required) in profile_skills
    if match:
        return f"Compétence {required} attribuée à {technician}.", True
    return f"Attention : {required} n'est pas attribuée à {technician}.", False


def operational_planning_drop_handler_bindings() -> DropHandlerBindings:
    """Compose the extracted drop workflow from transitional V1.x helpers."""
    return DropHandlerBindings(
        parse_date=_date_from_any,
        segment_by_id=_segment_by_id,
        segment_dates=v13._segment_dates,
        availability_hours=v13._availability_hours,
        availability_for_day=features.availability_for_day,
        number=v13._number,
        truthy=v15_engine._truthy,
        update_manual_allocation=v15_engine.update_manual_allocation,
        delete_manual_allocation=v15_engine.delete_manual_allocation,
        update_segment=v13.update_segment,
        add_segment=v13.add_segment,
        create_manual_allocation=v15_engine.create_manual_allocation,
        segment_overtime_field=v15_refinements.SEGMENT_OVERTIME_FIELD,
        rebuild_allocations=v15_refinements.rebuild_allocations_refined,
        allocation_by_id=v15_engine.allocation_by_id,
        is_missing_allocation=v15_refinements.is_missing_allocation,
        skill_message=_skill_message,
    )
