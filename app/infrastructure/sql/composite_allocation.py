from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...application.command_ports import CompositeAllocationCommandPort, PlanningCommandPort
from ...application.commands import AllocationDuplicateCommand, AllocationSplitCommand
from ...application.errors import ApplicationConflictError, ApplicationValidationError
from ...application.repository_ports import PlanningAuthorizationPort, PlanningMutationVersionPort
from ...domain.manual_overallocation import INCREASE_PLANNED, normalize_overallocation_policy
from ...domain.planning_engine import MISSING_ALLOCATION_TYPE
from .approval_revision_models import (
    APPROVAL_REFERENCE_CAPTURED,
    RequestApprovalReference,
)
from .base import new_id
from .command_adapters import INACTIVE_REQUIREMENT_STATUSES, SqlPlanningCommandAdapter
from .models import ORIGIN_REQUEST, Resource, ResourceRequirement, Shift
from .operational_choice_models import RequestOperationalState
from .overallocation import validate_projected_manual_state
from .planning_audit import ENTITY_SHIFT, SqlPlanningAuditJournal
from .planning_version import SqlPlanningMutationVersionRepository


_HOUR = Decimal("0.01")


def _text(value: object) -> str:
    return str(value or "").strip()


def _hours(value: object) -> Decimal:
    return Decimal(str(value).replace(",", ".")).quantize(_HOUR)


class SqlCompositeAllocationCommandAdapter(CompositeAllocationCommandPort):
    """Atomic split/duplicate implementation; caller owns the surrounding transaction."""

    def __init__(
        self,
        session: Session,
        *,
        planning: PlanningCommandPort | None = None,
        authorization: PlanningAuthorizationPort | None = None,
        versioning: PlanningMutationVersionPort | None = None,
        journal: SqlPlanningAuditJournal | None = None,
    ) -> None:
        self._session = session
        self._versioning = versioning or SqlPlanningMutationVersionRepository(session)
        self._planning = planning or SqlPlanningCommandAdapter(
            session,
            versioning=self._versioning,
        )
        self._authorization = authorization
        self._journal = journal or SqlPlanningAuditJournal(session)

    def _shift(self, identifier: str) -> Shift:
        wanted = _text(identifier)
        shift = self._session.scalar(
            select(Shift).where(
                (Shift.id == wanted) | (Shift.legacy_allocation_id == wanted)
            )
        )
        if shift is None:
            raise KeyError(f"Allocation {wanted} introuvable")
        return shift

    def _requirement(self, shift: Shift) -> ResourceRequirement:
        requirement = self._session.get(
            ResourceRequirement,
            shift.resource_requirement_id,
        )
        if requirement is None:
            raise KeyError(f"Segment {shift.resource_requirement_id} introuvable")
        if requirement.status in INACTIVE_REQUIREMENT_STATUSES:
            raise ValueError("Le segment de ce quart n'est plus actif.")
        return requirement

    def _resource(self, resource_id: str) -> Resource:
        wanted = _text(resource_id)
        if not wanted:
            raise ApplicationValidationError(
                "Un identifiant stable de ressource est requis.",
                code="allocation_resource_required",
            )
        resource = self._session.get(Resource, wanted)
        if resource is None:
            raise KeyError(f"Ressource {wanted} introuvable")
        if not resource.active:
            raise ValueError(f"La ressource {wanted} est inactive.")
        return resource

    def _locked_hours(self, requirement_id: str) -> Decimal:
        value = self._session.scalar(
            select(func.coalesce(func.sum(Shift.hours), 0)).where(
                Shift.resource_requirement_id == requirement_id,
                Shift.locked.is_(True),
            )
        )
        return _hours(value or 0)

    @staticmethod
    def _reference(shift: Shift) -> str:
        return _text(shift.legacy_allocation_id) or shift.id

    @staticmethod
    def _segment_reference(requirement: ResourceRequirement) -> str:
        return _text(requirement.legacy_segment_id) or requirement.id

    @staticmethod
    def _is_non_counted_proposal(shift: Shift) -> bool:
        return (
            _text(shift.source).upper() == "AUTO"
            and _text(shift.allocation_type) == MISSING_ALLOCATION_TYPE
        )

    def _authorization_context(
        self,
        requirement: ResourceRequirement,
        *,
        expected_approval_revision_id: str | None,
        expected_operational_version: int | None,
        require_operational_version: bool,
    ) -> tuple[str | None, int | None]:
        if requirement.origin != ORIGIN_REQUEST or not requirement.workforce_request_id:
            return None, None

        expected_revision = _text(expected_approval_revision_id)
        if not expected_revision:
            raise ApplicationValidationError(
                "La révision approuvée attendue est requise pour ce besoin.",
                code="allocation_approval_revision_required",
                context={"segment_id": self._segment_reference(requirement)},
            )

        reference = self._session.get(
            RequestApprovalReference,
            requirement.workforce_request_id,
        )
        active_revision = _text(reference.active_revision_id) if reference is not None else ""
        if (
            reference is None
            or reference.status != APPROVAL_REFERENCE_CAPTURED
            or not active_revision
            or expected_revision != active_revision
            or _text(requirement.approval_revision_id) != active_revision
            or requirement.approval_reference_status != APPROVAL_REFERENCE_CAPTURED
            or not _text(requirement.approved_entry_key)
        ):
            raise ApplicationConflictError(
                "L'autorisation approuvée du besoin a changé depuis sa lecture.",
                code="planning_authorization_unknown",
                context={
                    "segment_id": self._segment_reference(requirement),
                    "expected_approval_revision_id": expected_revision,
                    "current_approval_revision_id": active_revision or None,
                    "approved_entry_key": _text(requirement.approved_entry_key) or None,
                },
            )

        state = self._session.get(
            RequestOperationalState,
            requirement.workforce_request_id,
        )
        if state is not None and _text(state.approval_revision_id) != active_revision:
            raise ApplicationConflictError(
                "Les choix opérationnels ne correspondent plus à la révision approuvée active.",
                code="operational_choice_version_conflict",
                context={
                    "expected_approval_revision_id": active_revision,
                    "operational_approval_revision_id": state.approval_revision_id,
                },
            )
        current_operational = max(int(state.version or 1), 1) if state is not None else 1

        if require_operational_version and expected_operational_version is None:
            raise ApplicationValidationError(
                "La version opérationnelle attendue est requise pour augmenter le budget.",
                code="allocation_operational_version_required",
                context={"segment_id": self._segment_reference(requirement)},
            )
        if (
            expected_operational_version is not None
            and int(expected_operational_version) != current_operational
        ):
            raise ApplicationConflictError(
                "Les choix opérationnels ont été modifiés depuis leur lecture.",
                code="operational_choice_version_conflict",
                context={
                    "expected_version": int(expected_operational_version),
                    "current_version": current_operational,
                },
            )
        return active_revision, current_operational

    def _current_operational_version(
        self,
        requirement: ResourceRequirement,
    ) -> int | None:
        if not requirement.workforce_request_id:
            return None
        state = self._session.get(
            RequestOperationalState,
            requirement.workforce_request_id,
        )
        return max(int(state.version or 1), 1) if state is not None else 1

    def _validate_source(self, shift: Shift) -> None:
        if self._is_non_counted_proposal(shift):
            raise ApplicationValidationError(
                "Une proposition « Hors horaire requis » non comptabilisée ne peut pas être partagée ou dupliquée.",
                code="allocation_source_not_counted",
                context={"allocation_id": self._reference(shift)},
            )

    def _audit(
        self,
        *,
        operation: str,
        source_before: Mapping[str, object],
        source: Shift,
        target: Shift,
        requirement: ResourceRequirement,
        before_planned: Decimal,
        before_locked: Decimal,
        after_locked: Decimal,
        policy: str | None,
        approval_revision_id: str | None,
        expected_planning_version: int,
        operational_version: int | None,
        expected_operational_version: int | None,
        correlation_id: str | None,
        auto_source_converted: bool,
    ) -> None:
        current = self._journal.shift_snapshot(source.id)
        if current is None:
            raise RuntimeError("Le quart source est introuvable après la mutation composite.")
        entity_id, entity_reference, parent, source_after = current
        after = dict(source_after)
        after.update(
            {
                "composite_operation": operation,
                "target_allocation_id": self._reference(target),
                "target_shift_id": target.id,
                "target_resource_id": target.resource_id,
                "target_work_date": target.work_date.isoformat(),
                "target_hours": float(target.hours),
                "requirement_id": requirement.id,
                "planned_hours_before": float(before_planned),
                "planned_hours_after": float(requirement.planned_hours),
                "locked_hours_before": float(before_locked),
                "locked_hours_after": float(after_locked),
                "excess_hours_before": round(
                    max(float(before_locked - before_planned), 0.0),
                    2,
                ),
                "excess_hours_after": round(
                    max(float(after_locked - requirement.planned_hours), 0.0),
                    2,
                ),
                "overallocation_policy": policy,
                "approval_revision_id": approval_revision_id,
                "expected_planning_version": expected_planning_version,
                "planning_version": self._versioning.current_version(),
                "expected_operational_version": expected_operational_version,
                "operational_version": operational_version,
                "correlation_id": _text(correlation_id) or None,
                "auto_source_converted": auto_source_converted,
            }
        )
        self._journal.append(
            entity_type=ENTITY_SHIFT,
            entity_id=entity_id,
            entity_reference=entity_reference,
            parent_reference=parent,
            action=(
                "Partage atomique de quart"
                if operation == "SPLIT"
                else "Duplication atomique de quart"
            ),
            before=source_before,
            after=after,
        )

    def _result(
        self,
        *,
        operation: str,
        source: Shift,
        target: Shift,
        requirement: ResourceRequirement,
        approval_revision_id: str | None,
        auto_source_converted: bool,
    ) -> Mapping[str, Any]:
        locked = self._locked_hours(requirement.id)
        planned = _hours(requirement.planned_hours)
        return {
            "operation": operation,
            "source_allocation_id": self._reference(source),
            "target_allocation_id": self._reference(target),
            "source_shift_id": source.id,
            "target_shift_id": target.id,
            "segment_id": self._segment_reference(requirement),
            "requirement_id": requirement.id,
            "source_hours": float(source.hours),
            "target_hours": float(target.hours),
            "planned_hours": float(planned),
            "locked_hours": float(locked),
            "excess_hours": round(max(float(locked - planned), 0.0), 2),
            "planning_version": self._versioning.current_version(),
            "approval_revision_id": approval_revision_id,
            "operational_version": self._current_operational_version(requirement),
            "auto_source_converted": auto_source_converted,
        }

    def split(self, command: AllocationSplitCommand) -> Mapping[str, Any]:
        self._versioning.acquire(command.expected_planning_version)
        source = self._shift(command.allocation_id)
        requirement = self._requirement(source)
        self._validate_source(source)
        target_resource = self._resource(command.resource_id)

        source_before_row = self._journal.shift_snapshot(source.id)
        if source_before_row is None:
            raise RuntimeError("Le quart source est introuvable avant le partage.")
        source_before = dict(source_before_row[3])
        source_hours = _hours(source.hours)
        transfer = _hours(command.transfer_hours)
        if transfer <= 0 or transfer >= source_hours:
            raise ApplicationValidationError(
                "Le partage exige un transfert strictement inférieur aux heures du quart source; utilise le déplacement pour un transfert intégral.",
                code="allocation_split_hours_invalid",
                context={
                    "source_hours": float(source_hours),
                    "transfer_hours": float(transfer),
                },
            )

        before_planned = _hours(requirement.planned_hours)
        before_locked = self._locked_hours(requirement.id)
        projected_locked = (
            before_locked
            - (source_hours if source.locked else Decimal("0"))
            + source_hours
        )
        policy = normalize_overallocation_policy(command.overallocation_policy)
        approval_revision_id, _ = self._authorization_context(
            requirement,
            expected_approval_revision_id=command.expected_approval_revision_id,
            expected_operational_version=command.expected_operational_version,
            require_operational_version=policy == INCREASE_PLANNED,
        )
        target_outside = (
            bool(source.outside_standard_hours)
            if command.outside_standard_hours is None
            else bool(command.outside_standard_hours)
        )
        target_day, _impact = validate_projected_manual_state(
            self._session,
            requirement,
            target_resource,
            command.day,
            target_outside,
            current_locked_hours=before_locked,
            projected_locked_hours=projected_locked,
            overallocation_policy=policy,
            authorization=self._authorization,
            expected_operational_version=command.expected_operational_version,
        )

        auto_source_converted = _text(source.source).upper() == "AUTO"
        source.hours = source_hours - transfer
        source.source = "MANUAL"
        source.locked = True
        target = Shift(
            legacy_allocation_id=f"MAN-{new_id()}",
            resource_requirement_id=requirement.id,
            resource_id=target_resource.id,
            work_date=target_day,
            hours=transfer,
            allocation_type=source.allocation_type or requirement.planning_type,
            source="MANUAL",
            locked=True,
            outside_standard_hours=target_outside,
            confirmation=source.confirmation,
            note=source.note,
        )
        self._session.add(target)
        self._session.flush()
        self._planning.rebuild()

        persisted_source = self._session.get(Shift, source.id)
        persisted_target = self._session.get(Shift, target.id)
        if persisted_source is None or persisted_target is None:
            raise RuntimeError("Le recalcul a perdu un quart du partage atomique.")
        if (
            persisted_source.resource_requirement_id != requirement.id
            or persisted_target.resource_requirement_id != requirement.id
            or not persisted_source.locked
            or not persisted_target.locked
            or _text(persisted_source.source).upper() != "MANUAL"
            or _text(persisted_target.source).upper() != "MANUAL"
            or _hours(persisted_source.hours) + _hours(persisted_target.hours) != source_hours
        ):
            raise RuntimeError("Les invariants du partage atomique ne sont pas respectés.")

        after_locked = self._locked_hours(requirement.id)
        operational_version = self._current_operational_version(requirement)
        self._audit(
            operation="SPLIT",
            source_before=source_before,
            source=persisted_source,
            target=persisted_target,
            requirement=requirement,
            before_planned=before_planned,
            before_locked=before_locked,
            after_locked=after_locked,
            policy=policy,
            approval_revision_id=approval_revision_id,
            expected_planning_version=command.expected_planning_version,
            operational_version=operational_version,
            expected_operational_version=command.expected_operational_version,
            correlation_id=command.correlation_id,
            auto_source_converted=auto_source_converted,
        )
        return self._result(
            operation="SPLIT",
            source=persisted_source,
            target=persisted_target,
            requirement=requirement,
            approval_revision_id=approval_revision_id,
            auto_source_converted=auto_source_converted,
        )

    def duplicate(self, command: AllocationDuplicateCommand) -> Mapping[str, Any]:
        self._versioning.acquire(command.expected_planning_version)
        source = self._shift(command.allocation_id)
        requirement = self._requirement(source)
        self._validate_source(source)
        target_resource = self._resource(command.resource_id)

        source_before_row = self._journal.shift_snapshot(source.id)
        if source_before_row is None:
            raise RuntimeError("Le quart source est introuvable avant la duplication.")
        source_before = dict(source_before_row[3])
        source_hours = _hours(source.hours)
        before_planned = _hours(requirement.planned_hours)
        before_locked = self._locked_hours(requirement.id)
        projected_locked = (
            before_locked
            - (source_hours if source.locked else Decimal("0"))
            + source_hours
            + source_hours
        )
        policy = normalize_overallocation_policy(command.overallocation_policy)
        approval_revision_id, _ = self._authorization_context(
            requirement,
            expected_approval_revision_id=command.expected_approval_revision_id,
            expected_operational_version=command.expected_operational_version,
            require_operational_version=policy == INCREASE_PLANNED,
        )
        target_outside = (
            bool(source.outside_standard_hours)
            if command.outside_standard_hours is None
            else bool(command.outside_standard_hours)
        )
        target_day, _impact = validate_projected_manual_state(
            self._session,
            requirement,
            target_resource,
            command.day,
            target_outside,
            current_locked_hours=before_locked,
            projected_locked_hours=projected_locked,
            overallocation_policy=policy,
            authorization=self._authorization,
            expected_operational_version=command.expected_operational_version,
        )

        auto_source_converted = _text(source.source).upper() == "AUTO"
        source.source = "MANUAL"
        source.locked = True
        target = Shift(
            legacy_allocation_id=f"MAN-{new_id()}",
            resource_requirement_id=requirement.id,
            resource_id=target_resource.id,
            work_date=target_day,
            hours=source_hours,
            allocation_type=source.allocation_type or requirement.planning_type,
            source="MANUAL",
            locked=True,
            outside_standard_hours=target_outside,
            confirmation=source.confirmation,
            note=source.note,
        )
        self._session.add(target)
        self._session.flush()
        self._planning.rebuild()

        persisted_source = self._session.get(Shift, source.id)
        persisted_target = self._session.get(Shift, target.id)
        if persisted_source is None or persisted_target is None:
            raise RuntimeError("Le recalcul a perdu un quart de la duplication atomique.")
        if (
            persisted_source.resource_requirement_id != requirement.id
            or persisted_target.resource_requirement_id != requirement.id
            or not persisted_source.locked
            or not persisted_target.locked
            or _text(persisted_source.source).upper() != "MANUAL"
            or _text(persisted_target.source).upper() != "MANUAL"
            or _hours(persisted_source.hours) != source_hours
            or _hours(persisted_target.hours) != source_hours
        ):
            raise RuntimeError("Les invariants de la duplication atomique ne sont pas respectés.")

        after_locked = self._locked_hours(requirement.id)
        operational_version = self._current_operational_version(requirement)
        self._audit(
            operation="DUPLICATE",
            source_before=source_before,
            source=persisted_source,
            target=persisted_target,
            requirement=requirement,
            before_planned=before_planned,
            before_locked=before_locked,
            after_locked=after_locked,
            policy=policy,
            approval_revision_id=approval_revision_id,
            expected_planning_version=command.expected_planning_version,
            operational_version=operational_version,
            expected_operational_version=command.expected_operational_version,
            correlation_id=command.correlation_id,
            auto_source_converted=auto_source_converted,
        )
        return self._result(
            operation="DUPLICATE",
            source=persisted_source,
            target=persisted_target,
            requirement=requirement,
            approval_revision_id=approval_revision_id,
            auto_source_converted=auto_source_converted,
        )
