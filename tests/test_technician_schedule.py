from __future__ import annotations

from datetime import date
import unittest

from app.application.errors import ApplicationValidationError
from app.application.query_models import ResourceReadModel, ShiftReadModel
from app.application.security import AuthPrincipal, ROLE_TECHNICIAN
from app.application.technician_schedule import (
    LINK_STATUS_LINKED,
    LINK_STATUS_RESOURCE_NOT_FOUND,
    LINK_STATUS_UNLINKED,
    TechnicianScheduleService,
)


DAY = date(2026, 9, 16)


class StubQueries:
    def __init__(self, resources: tuple[ResourceReadModel, ...], shifts: tuple[ShiftReadModel, ...] = ()) -> None:
        self.resources = resources
        self.shifts = shifts
        self.last_resource_id: str | None = None

    def list_resources(self, *, active_only: bool = True):
        if active_only:
            return tuple(row for row in self.resources if row.active)
        return self.resources

    def list_shifts(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
        resource_name: str | None = None,
        resource_id: str | None = None,
    ):
        self.last_resource_id = resource_id
        rows = self.shifts
        if start is not None:
            rows = tuple(row for row in rows if row.work_date >= start)
        if end is not None:
            rows = tuple(row for row in rows if row.work_date <= end)
        if resource_name:
            rows = tuple(row for row in rows if row.resource_name == resource_name)
        if resource_id:
            rows = tuple(row for row in rows if row.resource_id == resource_id)
        return rows


class TechnicianScheduleTests(unittest.TestCase):
    def _principal(self, employee_external_id: str | None) -> AuthPrincipal:
        return AuthPrincipal.from_roles(
            local_user_id="user-1",
            issuer="issuer",
            subject="subject",
            display_name="Technicien",
            email=None,
            employee_external_id=employee_external_id,
            roles=(ROLE_TECHNICIAN,),
            auth_mode="test",
        )

    def test_unlinked_identity_returns_explicit_state(self) -> None:
        result = TechnicianScheduleService(StubQueries(())).read(
            principal=self._principal(None),
            start=DAY,
            end=DAY,
        )
        self.assertEqual(result.link_status, LINK_STATUS_UNLINKED)
        self.assertIsNone(result.resource)
        self.assertEqual(result.shifts, ())

    def test_missing_resource_returns_explicit_state(self) -> None:
        result = TechnicianScheduleService(StubQueries(())).read(
            principal=self._principal("EMP-404"),
            start=DAY,
            end=DAY,
        )
        self.assertEqual(result.link_status, LINK_STATUS_RESOURCE_NOT_FOUND)
        self.assertEqual(result.employee_external_id, "EMP-404")
        self.assertIsNone(result.resource)

    def test_linked_schedule_filters_by_resource_id_not_name(self) -> None:
        resources = (
            ResourceReadModel(id="R-1", name="Alex Martin", external_id="EMP-1"),
            ResourceReadModel(id="R-2", name="Alex Martin", external_id="EMP-2"),
        )
        shifts = (
            ShiftReadModel(
                allocation_id="A-1",
                segment_id="S-1",
                resource_id="R-1",
                resource_name="Alex Martin",
                work_date=DAY,
                hours=8,
                project_number="P-1",
            ),
            ShiftReadModel(
                allocation_id="A-2",
                segment_id="S-2",
                resource_id="R-2",
                resource_name="Alex Martin",
                work_date=DAY,
                hours=4,
                project_number="P-2",
            ),
        )
        queries = StubQueries(resources, shifts)
        result = TechnicianScheduleService(queries).read(
            principal=self._principal("EMP-2"),
            start=DAY,
            end=DAY,
        )
        self.assertEqual(result.link_status, LINK_STATUS_LINKED)
        self.assertEqual(result.resource.id if result.resource else None, "R-2")
        self.assertEqual(queries.last_resource_id, "R-2")
        self.assertEqual([row.allocation_id for row in result.shifts], ["A-2"])

    def test_inactive_linked_resource_remains_visible_for_history(self) -> None:
        resource = ResourceReadModel(
            id="R-3",
            name="Ancienne ressource",
            active=False,
            external_id="EMP-3",
        )
        result = TechnicianScheduleService(StubQueries((resource,))).read(
            principal=self._principal("EMP-3"),
            start=DAY,
            end=DAY,
        )
        self.assertEqual(result.link_status, LINK_STATUS_LINKED)
        self.assertFalse(result.resource.active if result.resource else True)

    def test_invalid_window_is_rejected(self) -> None:
        with self.assertRaises(ApplicationValidationError) as raised:
            TechnicianScheduleService(StubQueries(())).read(
                principal=self._principal(None),
                start=date(2026, 9, 17),
                end=date(2026, 9, 16),
            )
        self.assertEqual(raised.exception.code, "technician_schedule_date_window_invalid")


if __name__ == "__main__":
    unittest.main()
