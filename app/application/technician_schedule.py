from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .errors import ApplicationValidationError
from .query_models import ResourceReadModel, ShiftReadModel
from .query_ports import PlannerQueryPort
from .security import AuthPrincipal


LINK_STATUS_UNLINKED = "UNLINKED"
LINK_STATUS_RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
LINK_STATUS_LINKED = "LINKED"


@dataclass(frozen=True, slots=True)
class TechnicianScheduleReadModel:
    start: date
    end: date
    link_status: str
    employee_external_id: str | None
    resource: ResourceReadModel | None
    shifts: tuple[ShiftReadModel, ...]


class TechnicianScheduleService:
    """Read the connected user's own schedule without accepting a resource selector."""

    def __init__(self, queries: PlannerQueryPort) -> None:
        self._queries = queries

    def read(
        self,
        *,
        principal: AuthPrincipal,
        start: date,
        end: date,
    ) -> TechnicianScheduleReadModel:
        if end < start:
            raise ApplicationValidationError(
                "La date de fin ne peut pas précéder la date de début.",
                code="technician_schedule_date_window_invalid",
                context={"start": start.isoformat(), "end": end.isoformat()},
            )

        employee_external_id = str(principal.employee_external_id or "").strip() or None
        if employee_external_id is None:
            return TechnicianScheduleReadModel(
                start=start,
                end=end,
                link_status=LINK_STATUS_UNLINKED,
                employee_external_id=None,
                resource=None,
                shifts=(),
            )

        resource = next(
            (
                row
                for row in self._queries.list_resources(active_only=False)
                if str(row.external_id or "").strip() == employee_external_id
            ),
            None,
        )
        if resource is None:
            return TechnicianScheduleReadModel(
                start=start,
                end=end,
                link_status=LINK_STATUS_RESOURCE_NOT_FOUND,
                employee_external_id=employee_external_id,
                resource=None,
                shifts=(),
            )

        return TechnicianScheduleReadModel(
            start=start,
            end=end,
            link_status=LINK_STATUS_LINKED,
            employee_external_id=employee_external_id,
            resource=resource,
            shifts=tuple(
                self._queries.list_shifts(
                    start=start,
                    end=end,
                    resource_id=resource.id,
                )
            ),
        )
