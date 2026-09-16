from __future__ import annotations

from datetime import date
from decimal import Decimal
import json
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.infrastructure.sql import Base
from app.infrastructure.sql.models import Project, Resource, ResourceRequirement, Shift, WorkforceRequest
from app.infrastructure.sql.planning_audit import (
    AuditedAllocationCommandAdapter,
    AuditedSegmentRepository,
    PlanningChangeHistory,
    SqlPlanningAuditJournal,
)
from app.infrastructure.sql.segment_repository import SqlSegmentRepository


class _FakeAllocationCommands:
    def __init__(self, session: Session, requirement: ResourceRequirement, resource: Resource) -> None:
        self.session = session
        self.requirement = requirement
        self.resource = resource

    def create_manual(
        self,
        segment_id,
        technician,
        day_value,
        hours_value,
        hors_horaire=False,
        note="",
        confirmation=None,
    ):
        row = Shift(
            legacy_allocation_id="MAN-AUDIT-1",
            resource_requirement_id=self.requirement.id,
            resource_id=self.resource.id,
            work_date=day_value,
            hours=Decimal(str(hours_value)),
            allocation_type="Flexible",
            source="MANUAL",
            locked=True,
            outside_standard_hours=bool(hors_horaire),
            confirmation=confirmation,
            note=note or None,
        )
        self.session.add(row)
        self.session.flush()
        return row.legacy_allocation_id

    def update_manual(
        self,
        allocation_id,
        technician,
        day_value,
        hours_value,
        hors_horaire=False,
        note="",
        confirmation=None,
    ):
        row = self.session.scalar(select(Shift).where(Shift.legacy_allocation_id == allocation_id))
        assert row is not None
        row.work_date = day_value
        row.hours = Decimal(str(hours_value))
        row.outside_standard_hours = bool(hors_horaire)
        row.note = note or None
        row.confirmation = confirmation
        self.session.flush()

    def release_manual(self, allocation_id):
        row = self.session.scalar(select(Shift).where(Shift.legacy_allocation_id == allocation_id))
        if row is not None:
            self.session.delete(row)
            self.session.flush()

    def delete_manual(self, allocation_id):
        self.release_manual(allocation_id)

    def assign_segment(self, segment_id, technician):
        self.requirement.assigned_resource_id = self.resource.id
        self.requirement.status = "Planifié"
        self.session.flush()
        return {"planning_engine": "test"}


class PlanningAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.project = Project(number="P-100", name="Projet audit")
        self.resource = Resource(name="Technicien Audit", external_id="EMP-AUDIT")
        self.session.add_all([self.project, self.resource])
        self.session.flush()
        self.request = WorkforceRequest(
            legacy_demand_number="DMO-2026-9001",
            project_id=self.project.id,
            desired_start=date(2026, 9, 16),
            desired_end=date(2026, 9, 18),
            status="En planification",
        )
        self.session.add(self.request)
        self.session.flush()
        self.requirement = ResourceRequirement(
            legacy_segment_id="SEG-2026-9001",
            project_id=self.project.id,
            workforce_request_id=self.request.id,
            start_date=date(2026, 9, 16),
            end_date=date(2026, 9, 18),
            planned_hours=Decimal("8"),
            status="À assigner",
            planning_type="Flexible",
            priority="Normale",
            confirmation="Confirmée",
            origin="REQUEST",
        )
        self.session.add(self.requirement)
        self.session.flush()
        self.journal = SqlPlanningAuditJournal(self.session, actor_name="Planificateur Test")

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def test_segment_update_records_only_real_change_with_actor(self) -> None:
        repository = AuditedSegmentRepository(
            SqlSegmentRepository(self.session, actor_name="Planificateur Test"),
            self.journal,
        )
        repository.update("SEG-2026-9001", {"HeuresPrevues": Decimal("10")})

        events = self.session.scalars(select(PlanningChangeHistory)).all()
        self.assertEqual(1, len(events))
        self.assertEqual("SEGMENT", events[0].entity_type)
        self.assertEqual("SEG-2026-9001", events[0].entity_reference)
        self.assertEqual("Modification segment", events[0].action)
        self.assertEqual("Planificateur Test", events[0].actor_name)
        details = json.loads(events[0].details or "{}")
        self.assertEqual(8.0, details["changes"]["planned_hours"]["before"])
        self.assertEqual(10.0, details["changes"]["planned_hours"]["after"])

    def test_manual_shift_history_survives_operational_deletion(self) -> None:
        commands = AuditedAllocationCommandAdapter(
            _FakeAllocationCommands(self.session, self.requirement, self.resource),
            self.journal,
        )
        allocation_id = commands.create_manual(
            "SEG-2026-9001",
            self.resource.name,
            date(2026, 9, 16),
            4,
            note="Intervention",
        )
        commands.update_manual(
            allocation_id,
            self.resource.name,
            date(2026, 9, 17),
            6,
            note="Déplacé",
        )
        commands.delete_manual(allocation_id)

        self.assertIsNone(
            self.session.scalar(select(Shift).where(Shift.legacy_allocation_id == allocation_id))
        )
        events = self.session.scalars(
            select(PlanningChangeHistory)
            .where(PlanningChangeHistory.entity_reference == allocation_id)
            .order_by(PlanningChangeHistory.occurred_at, PlanningChangeHistory.id)
        ).all()
        self.assertEqual(3, len(events))
        self.assertEqual(
            ["Création quart manuel", "Modification quart manuel", "Suppression quart manuel"],
            [event.action for event in events],
        )
        self.assertTrue(all(event.actor_name == "Planificateur Test" for event in events))

    def test_assignment_is_a_segment_event_not_auto_shift_noise(self) -> None:
        commands = AuditedAllocationCommandAdapter(
            _FakeAllocationCommands(self.session, self.requirement, self.resource),
            self.journal,
        )
        commands.assign_segment("SEG-2026-9001", self.resource.name)

        events = self.session.scalars(select(PlanningChangeHistory)).all()
        self.assertEqual(1, len(events))
        self.assertEqual("Affectation segment", events[0].action)
        self.assertEqual("SEGMENT", events[0].entity_type)
        self.assertEqual("SEG-2026-9001", events[0].entity_reference)
        self.assertEqual(0, self.session.query(Shift).count())


if __name__ == "__main__":
    unittest.main()
