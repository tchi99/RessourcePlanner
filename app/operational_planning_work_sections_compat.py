from __future__ import annotations

from typing import Any

from . import v13, v14_engine, v15_refinements, v16, v16_refinements
from .operational_planning_drag_drop import make_draggable
from .operational_planning_work_sections import WorkSectionsBindings


def operational_planning_work_sections_bindings() -> WorkSectionsBindings:
    """Compose extracted work sections from transitional V1.x helpers."""
    return WorkSectionsBindings(
        all_projects=v16.ALL_PROJECTS,
        all_confirmations=v16.ALL_CONFIRMATIONS,
        demand_confirmation=v15_refinements.demand_confirmation,
        segment_competence=v14_engine.segment_competence,
        required_class=v16._required_class,
        number=v13._number,
        make_draggable=make_draggable,
        open_recommendation_dialog=lambda owner, segment: v16_refinements._open_recommendation_dialog(
            owner, segment
        ),
        open_segment_dialog=lambda owner, segment: v15_refinements._segment_dialog(
            owner, segment=segment
        ),
        open_request_dialog=lambda owner, demand: owner.open_edit_request_dialog(demand),
        date_text=lambda owner, value: owner._date_text(value),
    )
