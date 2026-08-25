from __future__ import annotations

from . import v13, v15_engine, v15_refinements, v16, v16_refinements
from .excel_repository import _date_from_any
from .operational_planning_cell_context import (
    CellContextBindings,
    OperationalPlanningCellContext,
)


def operational_planning_cell_context() -> OperationalPlanningCellContext:
    """Compose shared cell calculations from transitional V1.x helpers."""
    return OperationalPlanningCellContext(
        CellContextBindings(
            segment_records=v13.segment_records,
            allocation_records=v15_engine.allocation_records,
            is_missing_allocation=v15_refinements.is_missing_allocation,
            truthy=v15_engine._truthy,
            number=v13._number,
            availability_hours=v13._availability_hours,
            parse_date=_date_from_any,
            segment_dates=v13._segment_dates,
            resource_competence_map=v16_refinements.resource_competence_map,
            normalized_text=v16._normalized_text,
        )
    )
