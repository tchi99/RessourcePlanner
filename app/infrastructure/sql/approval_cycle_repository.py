from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...application.approval_cycles import (
    ApprovalApproverSnapshot,
    ApprovalCycleRecord,
    ApprovalCycleRequestRecord,
    ApprovalCycleRoutingInput,
    ApprovalCycleSubjectRecord,
    ApprovalRequirementRecord,
    ApprovalRequirementSnapshot,
)
from ...application.errors import ApplicationConflictError
from ...domain.approval_cycles import (
    APPROVAL_CYCLE_STATE_INVALIDATED,
    APPROVAL_CYCLE_STATE_OPEN,
)
from .approval_cycle_models import (
    ApprovalDecision,
    ApprovalRequirement,
    ApprovalRequirementApprover,
    RequestApprovalCycle,
)
from .approval_revision_repository import SqlRequestApprovalRevisionRepository
from .approval_scope_models import TaskApprovalScopeMapping
from .base import new_id, utc_now
from .models import (
    RequestLine,
    WorkforceRequest,
    WorkforceRequestHistory,
)
from .request_version import acquire_request_aggregate_version


def _text(value: object) -> str:
    return str(value or "").strip()


def _optional_text(value: object) -> str | None:
    normalized = _text(value)
    return normalized or None


def _decode_sources(value: str | None) -> tuple[str, ...]:
    try:
        raw = json.loads(value or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        raw = []
    if not isinstance(raw, list):
        return ()
    return tuple(sorted({str(item) for item in raw if str(item)}))


class SqlApprovalCycleRepository:
    def __init__(
        self,
        session: Session,
        *,
        actor_user_id: str | None = None,
        actor_name: str = "",
    ) -> None:
        self._session = session
        self._actor_user_id = _optional_text(actor_user_id)
        self._actor_name = _optional_text(actor_name)

    def get_request(
        self,
        request_id: str,
    ) -> ApprovalCycleRequestRecord | None:
        row = self._session.get(WorkforceRequest, _text(request_id))
        if row is None:
            return None
        return ApprovalCycleRequestRecord(
            id=row.id,
            number=_optional_text(row.legacy_demand_number) or row.id,
            status=_text(row.status),
            aggregate_version=max(int(row.aggregate_version or 1), 1),
            project_id=row.project_id,
            priority=_optional_text(row.priority),
            site_client=_optional_text(row.site_client),
            location=_optional_text(row.location),
            line_mode=bool(row.line_mode),
            approved_at=row.approved_at,
        )

    def list_active_line_ids(self, request_id: str) -> tuple[str, ...]:
        return tuple(
            self._session.scalars(
                select(RequestLine.id)
                .where(
                    RequestLine.workforce_request_id == _text(request_id),
                    RequestLine.active.is_(True),
                )
                .order_by(RequestLine.id)
            ).all()
        )

    def read_subject(self, request_id: str) -> ApprovalCycleSubjectRecord:
        request = self._session.get(WorkforceRequest, _text(request_id))
        if request is None:
            raise KeyError(f"Demande {request_id} introuvable")
        envelope = SqlRequestApprovalRevisionRepository(
            self._session
        ).candidate_envelope(request)
        return ApprovalCycleSubjectRecord(
            request_id=request.id,
            project_id=request.project_id,
            priority=_optional_text(request.priority),
            site_client=_optional_text(request.site_client),
            location=_optional_text(request.location),
            line_mode=bool(request.line_mode),
            authorization_entries=tuple(
                entry.authorization_payload()
                for entry in envelope.entries
            ),
        )

    def read_routing_inputs(
        self,
        request_id: str,
    ) -> tuple[ApprovalCycleRoutingInput, ...]:
        lines = self._session.scalars(
            select(RequestLine)
            .where(
                RequestLine.workforce_request_id == _text(request_id),
                RequestLine.active.is_(True),
            )
            .order_by(RequestLine.id)
        ).all()
        task_ids = {
            line.task_catalog_item_id
            for line in lines
            if line.task_catalog_item_id
        }
        mappings: dict[str, list[str]] = defaultdict(list)
        if task_ids:
            rows = self._session.execute(
                select(
                    TaskApprovalScopeMapping.task_catalog_item_id,
                    TaskApprovalScopeMapping.approval_scope_id,
                )
                .where(
                    TaskApprovalScopeMapping.task_catalog_item_id.in_(
                        task_ids
                    )
                )
                .order_by(
                    TaskApprovalScopeMapping.task_catalog_item_id,
                    TaskApprovalScopeMapping.approval_scope_id,
                )
            ).all()
            for task_id, scope_id in rows:
                mappings[task_id].append(scope_id)

        return tuple(
            ApprovalCycleRoutingInput(
                request_line_id=line.id,
                task_catalog_item_id=line.task_catalog_item_id,
                approval_scope_ids=tuple(
                    sorted(
                        set(
                            mappings.get(
                                line.task_catalog_item_id or "",
                                [],
                            )
                        )
                    )
                ),
                proposed_resource_id=_optional_text(
                    line.proposed_resource_id
                ),
            )
            for line in lines
        )

    def _cycle_requirements(
        self,
        cycle_id: str,
    ) -> tuple[ApprovalRequirementRecord, ...]:
        requirements = self._session.scalars(
            select(ApprovalRequirement)
            .where(
                ApprovalRequirement.approval_cycle_id == cycle_id
            )
            .order_by(
                ApprovalRequirement.request_line_id,
                ApprovalRequirement.id,
            )
        ).all()
        requirement_ids = {row.id for row in requirements}
        approvers_by_requirement: dict[
            str,
            list[ApprovalApproverSnapshot],
        ] = defaultdict(list)
        if requirement_ids:
            rows = self._session.scalars(
                select(ApprovalRequirementApprover)
                .where(
                    ApprovalRequirementApprover.requirement_id.in_(
                        requirement_ids
                    )
                )
                .order_by(
                    ApprovalRequirementApprover.requirement_id,
                    ApprovalRequirementApprover.app_user_id,
                )
            ).all()
            for row in rows:
                approvers_by_requirement[row.requirement_id].append(
                    ApprovalApproverSnapshot(
                        app_user_id=row.app_user_id,
                        sources=_decode_sources(row.sources_text),
                    )
                )

        return tuple(
            ApprovalRequirementRecord(
                id=row.id,
                request_line_id=row.request_line_id,
                task_catalog_item_id=row.task_catalog_item_id,
                approval_scope_id=row.approval_scope_id,
                proposed_resource_id=row.proposed_resource_id,
                routing_sources=_decode_sources(
                    row.routing_sources_text
                ),
                approvers=tuple(
                    approvers_by_requirement.get(row.id, [])
                ),
            )
            for row in requirements
        )

    def _record(
        self,
        cycle: RequestApprovalCycle,
    ) -> ApprovalCycleRecord:
        return ApprovalCycleRecord(
            id=cycle.id,
            workforce_request_id=cycle.workforce_request_id,
            submitted_request_version=int(
                cycle.submitted_request_version
            ),
            state=cycle.state,
            subject_fingerprint=cycle.subject_fingerprint,
            initialization_reason=cycle.initialization_reason,
            submitted_at=cycle.submitted_at,
            invalidated_at=cycle.invalidated_at,
            invalidation_reason=cycle.invalidation_reason,
            completed_at=cycle.completed_at,
            approved_revision_id=cycle.approved_revision_id,
            requirements=self._cycle_requirements(cycle.id),
        )

    def get_active_cycle(
        self,
        request_id: str,
    ) -> ApprovalCycleRecord | None:
        rows = self._session.scalars(
            select(RequestApprovalCycle)
            .where(
                RequestApprovalCycle.workforce_request_id
                == _text(request_id),
                RequestApprovalCycle.state
                == APPROVAL_CYCLE_STATE_OPEN,
            )
            .order_by(
                RequestApprovalCycle.submitted_at.desc(),
                RequestApprovalCycle.id.desc(),
            )
            .limit(2)
        ).all()
        if len(rows) > 1:
            raise ApplicationConflictError(
                "Plus d'un cycle d'approbation actif existe pour la demande.",
                code="approval_cycle_multiple_active",
                context={"workforce_request_id": _text(request_id)},
            )
        return self._record(rows[0]) if rows else None

    def has_any_cycle(self, request_id: str) -> bool:
        count = self._session.scalar(
            select(func.count(RequestApprovalCycle.id)).where(
                RequestApprovalCycle.workforce_request_id
                == _text(request_id)
            )
        )
        return bool(count)

    def _append_history(
        self,
        request: WorkforceRequest,
        *,
        action: str,
        comment: str | None,
        cycle_id: str,
        extra_details: dict[str, object] | None = None,
    ) -> None:
        details = {
            "aggregate_version": int(
                request.aggregate_version or 1
            ),
            "line_mode": bool(request.line_mode),
            "approval_cycle_id": cycle_id,
        }
        if extra_details:
            details.update(extra_details)
        self._session.add(
            WorkforceRequestHistory(
                workforce_request_id=request.id,
                action=action,
                status=request.status,
                comment=_optional_text(comment),
                details=json.dumps(
                    details,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                actor_user_id=self._actor_user_id,
                actor_name=self._actor_name,
                occurred_at=utc_now(),
            )
        )

    def create_cycle(
        self,
        *,
        request_id: str,
        submitted_request_version: int,
        expected_version: int,
        subject_fingerprint: str,
        initialization_reason: str,
        requirements: Sequence[ApprovalRequirementSnapshot],
    ) -> ApprovalCycleRecord:
        request = self._session.get(
            WorkforceRequest,
            _text(request_id),
        )
        if request is None:
            raise KeyError(f"Demande {request_id} introuvable")
        if self.get_active_cycle(request.id) is not None:
            raise ApplicationConflictError(
                "Un cycle d'approbation actif existe déjà pour cette demande.",
                code="approval_cycle_already_active",
                context={"workforce_request_id": request.id},
            )
        if int(submitted_request_version) != int(expected_version):
            raise ApplicationConflictError(
                "La version soumise ne correspond pas à la version attendue.",
                code="approval_cycle_submitted_version_conflict",
                context={
                    "submitted_request_version": int(
                        submitted_request_version
                    ),
                    "expected_version": int(expected_version),
                },
            )

        acquire_request_aggregate_version(
            self._session,
            request,
            expected_version,
        )
        cycle = RequestApprovalCycle(
            id=new_id(),
            workforce_request_id=request.id,
            submitted_request_version=int(
                submitted_request_version
            ),
            state=APPROVAL_CYCLE_STATE_OPEN,
            subject_fingerprint=_text(subject_fingerprint),
            initialization_reason=_text(
                initialization_reason
            ),
            submitted_at=utc_now(),
        )
        self._session.add(cycle)
        self._session.flush()

        for snapshot in requirements:
            requirement = ApprovalRequirement(
                id=new_id(),
                approval_cycle_id=cycle.id,
                request_line_id=snapshot.request_line_id,
                task_catalog_item_id=snapshot.task_catalog_item_id,
                approval_scope_id=snapshot.approval_scope_id,
                proposed_resource_id=snapshot.proposed_resource_id,
                routing_sources_text=json.dumps(
                    sorted(set(snapshot.routing_sources)),
                    separators=(",", ":"),
                ),
            )
            self._session.add(requirement)
            for approver in snapshot.approvers:
                self._session.add(
                    ApprovalRequirementApprover(
                        requirement_id=requirement.id,
                        app_user_id=approver.app_user_id,
                        sources_text=json.dumps(
                            sorted(set(approver.sources)),
                            separators=(",", ":"),
                        ),
                    )
                )

        self._append_history(
            request,
            action="Initialisation cycle approbation",
            comment=None,
            cycle_id=cycle.id,
            extra_details={
                "submitted_request_version": int(
                    submitted_request_version
                ),
                "subject_fingerprint": cycle.subject_fingerprint,
                "initialization_reason": cycle.initialization_reason,
                "requirement_count": len(requirements),
            },
        )
        self._session.flush()
        self._session.refresh(cycle)
        return self._record(cycle)

    def invalidate_cycle(
        self,
        *,
        cycle_id: str,
        expected_version: int,
        reason: str,
    ) -> ApprovalCycleRecord:
        cycle = self._session.get(
            RequestApprovalCycle,
            _text(cycle_id),
        )
        if cycle is None:
            raise KeyError(
                f"Cycle d'approbation {cycle_id} introuvable"
            )
        if cycle.state != APPROVAL_CYCLE_STATE_OPEN:
            raise ApplicationConflictError(
                "Le cycle d'approbation n'est plus actif.",
                code="approval_cycle_not_open",
                context={
                    "approval_cycle_id": cycle.id,
                    "state": cycle.state,
                },
            )
        request = self._session.get(
            WorkforceRequest,
            cycle.workforce_request_id,
        )
        if request is None:
            raise KeyError(
                f"Demande {cycle.workforce_request_id} introuvable"
            )

        acquire_request_aggregate_version(
            self._session,
            request,
            expected_version,
        )
        cycle.state = APPROVAL_CYCLE_STATE_INVALIDATED
        cycle.invalidated_at = utc_now()
        cycle.invalidation_reason = _text(reason)
        self._append_history(
            request,
            action="Invalidation cycle approbation",
            comment=_text(reason),
            cycle_id=cycle.id,
            extra_details={
                "submitted_request_version": int(
                    cycle.submitted_request_version
                ),
                "subject_fingerprint": cycle.subject_fingerprint,
                "invalidation_reason": cycle.invalidation_reason,
            },
        )
        self._session.flush()
        self._session.refresh(cycle)
        return self._record(cycle)
