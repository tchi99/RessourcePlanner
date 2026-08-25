from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Mapping

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ...application.command_ports import AllocationCommandPort, PlanningCommandPort
from ...domain.availability_rules import availability_hours_for_day
from ...domain.planning_engine import MISSING_ALLOCATION_TYPE, build_allocation_plan
from ...domain.planning_projection import project_planning_snapshot
from ...domain.value_coercion import date_from_value
from .base import new_id
from .models import Resource, ResourceRequirement, Shift
from .planning_repository import SqlPlanningReadRepository


INACTIVE_REQUIREMENT_STATUSES = {"Annulé", "Terminé"}


def _text(value: object) -> str:
    return str(value or "").strip()


def _decimal(value: object) -> Decimal:
    return Decimal(str(value).replace(",", "."))


class SqlPlanningCommandAdapter(PlanningCommandPort):
    """Authoritative pure-engine rebuild persisted atomically in SQL.

    The caller owns the Session transaction. Existing active locked shifts are never
    deleted by an automatic rebuild; all other shifts are regenerated from the pure
    engine result. Any failure therefore rolls the whole unit of work back naturally.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def _active_locked_shifts(self) -> list[Shift]:
        return list(
            self._session.scalars(
                select(Shift)
                .join(
                    ResourceRequirement,
                    Shift.resource_requirement_id == ResourceRequirement.id,
                )
                .where(
                    Shift.locked.is_(True),
                    ResourceRequirement.status.not_in(INACTIVE_REQUIREMENT_STATUSES),
                )
                .order_by(Shift.id)
            ).all()
        )

    def rebuild(self) -> Mapping[str, Any]:
        snapshot = SqlPlanningReadRepository(self._session).capture()
        calculation = project_planning_snapshot(snapshot)
        if calculation.unsupported_segment_ids:
            raise RuntimeError(
                "Le moteur pur ne peut pas recalculer des segments actifs non supportés: "
                + ", ".join(calculation.unsupported_segment_ids)
            )

        result = build_allocation_plan(
            calculation.segments,
            calculation.locked_allocations,
            calculation.capacity_by_resource_day,
            outside_schedule_eligible_by_resource_day=(
                calculation.outside_schedule_eligible_by_resource_day
            ),
        )

        protected = self._active_locked_shifts()
        protected_ids = {shift.id for shift in protected}

        # Keep only active locked user decisions. Unlocked rows are disposable engine
        # output; locked rows belonging to cancelled/completed requirements are removed
        # as part of that explicit workflow transition.
        existing = self._session.scalars(select(Shift)).all()
        for shift in existing:
            if shift.id not in protected_ids:
                self._session.delete(shift)
        self._session.flush()

        requirements = self._session.scalars(select(ResourceRequirement)).all()
        requirement_by_identifier = {
            _text(requirement.legacy_segment_id) or requirement.id: requirement
            for requirement in requirements
        }
        resources = self._session.scalars(select(Resource)).all()
        resource_by_name = {resource.name: resource for resource in resources}

        for allocation in result.allocations:
            if allocation.locked:
                continue
            requirement = requirement_by_identifier.get(allocation.segment_id)
            if requirement is None:
                raise RuntimeError(
                    f"Segment {allocation.segment_id} introuvable pendant la persistance du plan."
                )
            resource = resource_by_name.get(allocation.resource_id)
            if resource is None:
                raise RuntimeError(
                    f"Ressource {allocation.resource_id} introuvable pendant la persistance du plan."
                )

            missing = not allocation.counts_as_allocated
            self._session.add(
                Shift(
                    resource_requirement_id=requirement.id,
                    resource_id=resource.id,
                    work_date=allocation.day,
                    hours=_decimal(allocation.hours),
                    allocation_type=allocation.allocation_type,
                    source="AUTO",
                    locked=False,
                    outside_standard_hours=bool(allocation.outside_schedule),
                    note=(
                        "Capacité standard insuffisante — quart hors horaire à confirmer"
                        if missing
                        else (
                            "Hors horaire autorisé au niveau du segment"
                            if allocation.outside_schedule
                            else None
                        )
                    ),
                )
            )
        self._session.flush()

        persisted_protected = set(
            self._session.scalars(
                select(Shift.id).where(Shift.id.in_(protected_ids))
            ).all()
        ) if protected_ids else set()
        missing_locked = sorted(protected_ids - persisted_protected)
        if missing_locked:
            raise RuntimeError(
                "Le recalcul SQL aurait supprimé des quarts verrouillés actifs: "
                + ", ".join(missing_locked)
            )

        return {
            "segments": result.segment_count,
            "allocations": len(
                [row for row in result.allocations if row.counts_as_allocated]
            ),
            "locked_allocations": len(protected_ids),
            "requested_hours": round(result.requested_hours, 2),
            "allocated_hours": round(result.allocated_hours, 2),
            "overtime_hours": round(result.overtime_hours, 2),
            "unallocated_hours": round(result.unallocated_hours, 2),
            "planning_engine": "pure",
        }


class SqlAllocationCommandAdapter(AllocationCommandPort):
    """Manual-shift and segment-assignment commands backed by one SQL transaction."""

    def __init__(
        self,
        session: Session,
        *,
        planning: PlanningCommandPort | None = None,
    ) -> None:
        self._session = session
        self._planning = planning or SqlPlanningCommandAdapter(session)

    def _requirement(self, identifier: str) -> ResourceRequirement:
        wanted = _text(identifier)
        requirement = self._session.scalar(
            select(ResourceRequirement).where(
                (ResourceRequirement.legacy_segment_id == wanted)
                | (ResourceRequirement.id == wanted)
            )
        )
        if requirement is None:
            raise KeyError(f"Segment {wanted} introuvable")
        if requirement.status in INACTIVE_REQUIREMENT_STATUSES:
            raise ValueError(f"Le segment {wanted} n'est plus actif.")
        return requirement

    def _resource(self, name: str) -> Resource:
        wanted = _text(name)
        resource = self._session.scalar(select(Resource).where(Resource.name == wanted))
        if resource is None:
            raise KeyError(f"Ressource {wanted} introuvable")
        if not resource.active:
            raise ValueError(f"La ressource {wanted} est inactive.")
        return resource

    def _shift(self, identifier: str) -> Shift | None:
        wanted = _text(identifier)
        if not wanted:
            return None
        return self._session.scalar(
            select(Shift).where(
                (Shift.legacy_allocation_id == wanted) | (Shift.id == wanted)
            )
        )

    def _validate_manual(
        self,
        requirement: ResourceRequirement,
        resource: Resource,
        day_value: Any,
        hours_value: Any,
        outside_standard_hours: bool,
        *,
        exclude_shift_id: str | None = None,
    ) -> tuple[date, Decimal]:
        day = date_from_value(day_value)
        if day is None:
            raise ValueError("La date du quart est requise.")
        hours = _decimal(hours_value)
        if hours <= 0:
            raise ValueError("Les heures doivent être supérieures à zéro.")
        if day < requirement.start_date or day > requirement.end_date:
            raise ValueError("Le quart manuel doit demeurer dans la fenêtre du segment.")

        locked_statement = select(func.coalesce(func.sum(Shift.hours), 0)).where(
            Shift.resource_requirement_id == requirement.id,
            Shift.locked.is_(True),
        )
        if exclude_shift_id:
            locked_statement = locked_statement.where(Shift.id != exclude_shift_id)
        locked_hours = Decimal(str(self._session.scalar(locked_statement) or 0))
        if locked_hours + hours > requirement.planned_hours + Decimal("0.001"):
            raise ValueError(
                "Les heures verrouillées ne peuvent pas dépasser les heures prévues du segment."
            )

        snapshot = SqlPlanningReadRepository(self._session).capture()
        if (
            availability_hours_for_day(snapshot.availability, resource.name, day) <= 0
            and not outside_standard_hours
        ):
            raise ValueError(
                "La ressource n'est pas disponible selon son horaire standard cette journée. "
                "Autorise explicitement le quart hors horaire pour continuer."
            )
        return day, hours

    def create_manual(
        self,
        segment_id: str,
        technician: str,
        day_value: Any,
        hours_value: Any,
        hors_horaire: bool = False,
        note: str = "",
    ) -> str:
        requirement = self._requirement(segment_id)
        resource = self._resource(technician)
        day, hours = self._validate_manual(
            requirement,
            resource,
            day_value,
            hours_value,
            bool(hors_horaire),
        )

        requirement.assigned_resource_id = resource.id
        if requirement.status == "À assigner":
            requirement.status = "Planifié"

        identifier = f"MAN-{new_id()}"
        shift = Shift(
            legacy_allocation_id=identifier,
            resource_requirement_id=requirement.id,
            resource_id=resource.id,
            work_date=day,
            hours=hours,
            allocation_type=requirement.planning_type,
            source="MANUAL",
            locked=True,
            outside_standard_hours=bool(hors_horaire),
            note=_text(note) or None,
        )
        self._session.add(shift)
        self._session.flush()
        self._planning.rebuild()
        return identifier

    def update_manual(
        self,
        allocation_id: str,
        technician: str,
        day_value: Any,
        hours_value: Any,
        hors_horaire: bool = False,
        note: str = "",
    ) -> None:
        shift = self._shift(allocation_id)
        if shift is None:
            raise KeyError(f"Allocation {allocation_id} introuvable")
        requirement = self._requirement(shift.resource_requirement_id)
        resource = self._resource(technician)
        day, hours = self._validate_manual(
            requirement,
            resource,
            day_value,
            hours_value,
            bool(hors_horaire),
            exclude_shift_id=shift.id,
        )

        requirement.assigned_resource_id = resource.id
        if requirement.status == "À assigner":
            requirement.status = "Planifié"
        shift.resource_id = resource.id
        shift.work_date = day
        shift.hours = hours
        shift.allocation_type = requirement.planning_type
        shift.source = "MANUAL"
        shift.locked = True
        shift.outside_standard_hours = bool(hors_horaire)
        shift.note = _text(note) or None
        self._session.flush()
        self._planning.rebuild()

    def release_manual(self, allocation_id: str) -> None:
        shift = self._shift(allocation_id)
        if shift is None:
            return
        shift.locked = False
        self._session.flush()
        self._planning.rebuild()

    def delete_manual(self, allocation_id: str) -> None:
        shift = self._shift(allocation_id)
        if shift is None:
            return
        self._session.delete(shift)
        self._session.flush()
        self._planning.rebuild()

    def assign_segment(self, segment_id: str, technician: str) -> Mapping[str, Any]:
        requirement = self._requirement(segment_id)
        resource = self._resource(technician)
        requirement.assigned_resource_id = resource.id
        requirement.status = "Planifié"
        self._session.flush()
        return self._planning.rebuild()
