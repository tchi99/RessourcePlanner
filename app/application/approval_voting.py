from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence
from uuid import uuid4

from .approval_cycles import ApprovalCycleRecord, ApprovalCycleService
from .command_ports import ApprovedDemandSyncPort, PlanningCommandPort
from .errors import (
    ApplicationAuthorizationError,
    ApplicationConflictError,
    ApplicationNotFoundError,
    ApplicationValidationError,
)
from .repository_ports import PlanningMutationVersionPort
from .security import PERMISSION_APPROVE_DEMANDS


APPROVAL_DECISION_APPROVE = "APPROVE"


@dataclass(frozen=True, slots=True)
class ApprovalDecisionRecord:
    requirement_id: str
    app_user_id: str
    decision: str
    action_id: str
    decided_at: object | None = None
    comment: str | None = None


@dataclass(frozen=True, slots=True)
class ApprovalQuorumProjection:
    total_requirements: int
    satisfied_requirement_ids: tuple[str, ...]
    remaining_requirement_ids: tuple[str, ...]

    @property
    def satisfied_requirements(self) -> int:
        return len(self.satisfied_requirement_ids)

    @property
    def complete(self) -> bool:
        return self.total_requirements > 0 and not self.remaining_requirement_ids


@dataclass(frozen=True, slots=True)
class ApprovalVoteCommand:
    workforce_request_id: str
    approval_cycle_id: str
    expected_request_version: int
    requirement_ids: tuple[str, ...] = ()
    request_line_ids: tuple[str, ...] = ()
    decision: str = APPROVAL_DECISION_APPROVE
    comment: str = ""
    expected_planning_version: int | None = None


@dataclass(frozen=True, slots=True)
class ApprovalVoteOutcome:
    workforce_request_id: str
    demand_number: str
    approval_cycle_id: str
    action_id: str | None
    request_version: int
    status: str
    quorum: ApprovalQuorumProjection
    approval_revision_id: str | None = None
    planning_version: int | None = None
    planning: Mapping[str, Any] | None = None
    conflict_code: str | None = None
    conflict_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "workforce_request_id": self.workforce_request_id,
            "demand_number": self.demand_number,
            "approval_cycle_id": self.approval_cycle_id,
            "action_id": self.action_id,
            "request_version": self.request_version,
            "status": self.status,
            "total_requirements": self.quorum.total_requirements,
            "satisfied_requirements": self.quorum.satisfied_requirements,
            "satisfied_requirement_ids": list(self.quorum.satisfied_requirement_ids),
            "remaining_requirement_ids": list(self.quorum.remaining_requirement_ids),
            "quorum_complete": self.quorum.complete,
            "approval_revision_id": self.approval_revision_id,
            "planning_version": self.planning_version,
            "planning": dict(self.planning or {}) if self.planning is not None else None,
            "conflict_code": self.conflict_code,
            "conflict_message": self.conflict_message,
        }


class ApprovalVoteRepositoryPort(Protocol):
    def actor_is_active(self, app_user_id: str) -> bool: ...

    def list_decisions(self, cycle_id: str) -> tuple[ApprovalDecisionRecord, ...]: ...

    def acquire_request_version(self, request_id: str, expected_version: int) -> int: ...

    def append_decisions(
        self,
        *,
        cycle_id: str,
        requirement_ids: Sequence[str],
        app_user_id: str,
        decision: str,
        comment: str,
        action_id: str,
    ) -> None: ...

    def mark_request_approved(
        self,
        request_id: str,
        *,
        actor_name: str,
        comment: str,
    ) -> None: ...

    def active_revision_id(self, request_id: str) -> str | None: ...

    def complete_cycle(
        self,
        *,
        cycle_id: str,
        approval_revision_id: str,
        action_id: str,
        planning_version: int | None,
    ) -> None: ...

    def append_vote_audit(
        self,
        *,
        request_id: str,
        cycle_id: str,
        action_id: str,
        requirement_ids: Sequence[str],
        old_request_version: int,
        new_request_version: int,
        quorum: ApprovalQuorumProjection,
        planning_version: int | None = None,
        approval_revision_id: str | None = None,
    ) -> None: ...


def project_approval_quorum(
    cycle: ApprovalCycleRecord,
    decisions: Sequence[ApprovalDecisionRecord],
) -> ApprovalQuorumProjection:
    positive_by_requirement: dict[str, set[str]] = {}
    for row in decisions:
        if str(row.decision).strip().upper() != APPROVAL_DECISION_APPROVE:
            continue
        positive_by_requirement.setdefault(row.requirement_id, set()).add(row.app_user_id)

    satisfied: list[str] = []
    remaining: list[str] = []
    for requirement in cycle.requirements:
        frozen_approvers = {row.app_user_id for row in requirement.approvers}
        positive = positive_by_requirement.get(requirement.id, set())
        if frozen_approvers.intersection(positive):
            satisfied.append(requirement.id)
        else:
            remaining.append(requirement.id)

    return ApprovalQuorumProjection(
        total_requirements=len(cycle.requirements),
        satisfied_requirement_ids=tuple(sorted(satisfied)),
        remaining_requirement_ids=tuple(sorted(remaining)),
    )


class ApprovalVoteService:
    """#276C line-scoped voting and atomic quorum finalization.

    Partial votes mutate only the approval aggregate.  The planning guard and the
    canonical #13 materialization path are entered only when the current command can
    complete the frozen cycle quorum.
    """

    def __init__(
        self,
        *,
        cycles: ApprovalCycleService,
        repository: ApprovalVoteRepositoryPort,
        planning_versions: PlanningMutationVersionPort,
        approved_sync: ApprovedDemandSyncPort,
        planning: PlanningCommandPort,
        current_user_id: str | None,
        current_user_name: str,
        permissions: Sequence[str],
    ) -> None:
        self._cycles = cycles
        self._repository = repository
        self._planning_versions = planning_versions
        self._approved_sync = approved_sync
        self._planning = planning
        self._current_user_id = str(current_user_id or "").strip() or None
        self._current_user_name = str(current_user_name or "").strip()
        self._permissions = tuple(permissions)

    def _actor_id(self) -> str:
        if self._current_user_id is None:
            raise ApplicationAuthorizationError(
                "Une identité AppUser stable est requise pour approuver.",
                code="approval_actor_identity_required",
            )
        if PERMISSION_APPROVE_DEMANDS not in self._permissions:
            raise ApplicationAuthorizationError(
                "La permission approve_demands est requise.",
                code="approval_permission_required",
            )
        if not self._repository.actor_is_active(self._current_user_id):
            raise ApplicationAuthorizationError(
                "L'utilisateur applicatif courant est inactif.",
                code="approval_actor_inactive",
                context={"app_user_id": self._current_user_id},
            )
        return self._current_user_id

    def _active_cycle(self, request_id: str, cycle_id: str) -> ApprovalCycleRecord:
        cycle = self._cycles.get_active_cycle(request_id)
        if cycle is None:
            if self._cycles.legacy_compatibility_state(request_id) == "LEGACY_SUBMITTED":
                raise ApplicationConflictError(
                    "La demande Soumise doit d'abord recevoir un cycle d'approbation explicite.",
                    code="approval_cycle_initialization_required",
                    context={"workforce_request_id": request_id},
                )
            raise ApplicationConflictError(
                "Aucun cycle d'approbation actif n'existe pour la demande.",
                code="approval_cycle_missing",
                context={"workforce_request_id": request_id},
            )
        if cycle.id != str(cycle_id or "").strip():
            raise ApplicationConflictError(
                "Le cycle d'approbation fourni n'est plus le cycle actif.",
                code="approval_cycle_conflict",
                context={
                    "approval_cycle_id": str(cycle_id or "").strip(),
                    "active_approval_cycle_id": cycle.id,
                },
            )
        return cycle

    @staticmethod
    def _target_requirements(
        cycle: ApprovalCycleRecord,
        *,
        requirement_ids: Sequence[str],
        request_line_ids: Sequence[str],
    ) -> tuple[str, ...]:
        requested_ids = {str(value).strip() for value in requirement_ids if str(value).strip()}
        requested_lines = {str(value).strip() for value in request_line_ids if str(value).strip()}
        if not requested_ids and not requested_lines:
            raise ApplicationValidationError(
                "Au moins une exigence ou une ligne doit être ciblée.",
                code="approval_vote_targets_required",
            )

        by_id = {row.id: row for row in cycle.requirements}
        by_line = {row.request_line_id: row for row in cycle.requirements}
        unknown_ids = sorted(requested_ids - set(by_id))
        unknown_lines = sorted(requested_lines - set(by_line))
        if unknown_ids or unknown_lines:
            raise ApplicationValidationError(
                "La commande cible une exigence qui n'appartient pas au cycle actif.",
                code="approval_vote_target_invalid",
                context={
                    "unknown_requirement_ids": unknown_ids,
                    "unknown_request_line_ids": unknown_lines,
                },
            )
        resolved = set(requested_ids)
        resolved.update(by_line[line_id].id for line_id in requested_lines)
        return tuple(sorted(resolved))

    @staticmethod
    def _eligible_requirements(
        cycle: ApprovalCycleRecord,
        actor_id: str,
    ) -> tuple[str, ...]:
        return tuple(
            sorted(
                requirement.id
                for requirement in cycle.requirements
                if actor_id in {row.app_user_id for row in requirement.approvers}
            )
        )

    @staticmethod
    def _assert_actor_eligible(
        cycle: ApprovalCycleRecord,
        actor_id: str,
        requirement_ids: Sequence[str],
    ) -> None:
        by_id = {row.id: row for row in cycle.requirements}
        forbidden = [
            requirement_id
            for requirement_id in requirement_ids
            if actor_id not in {
                row.app_user_id for row in by_id[requirement_id].approvers
            }
        ]
        if forbidden:
            raise ApplicationAuthorizationError(
                "L'acteur n'est pas admissible pour toutes les exigences ciblées.",
                code="approval_actor_not_eligible",
                context={
                    "app_user_id": actor_id,
                    "requirement_ids": tuple(sorted(forbidden)),
                },
            )

    def _current_subject_matches(self, cycle: ApprovalCycleRecord) -> bool:
        return self._cycles.current_subject_fingerprint(cycle.workforce_request_id) == cycle.subject_fingerprint

    def _invalidated_outcome(
        self,
        *,
        cycle: ApprovalCycleRecord,
        expected_version: int,
        demand_number: str,
    ) -> ApprovalVoteOutcome:
        self._cycles.invalidate_cycle(
            cycle.workforce_request_id,
            expected_version=expected_version,
            reason="SUBJECT_CHANGED",
        )
        request = self._cycles.get_request(cycle.workforce_request_id)
        decisions = self._repository.list_decisions(cycle.id)
        quorum = project_approval_quorum(cycle, decisions)
        return ApprovalVoteOutcome(
            workforce_request_id=cycle.workforce_request_id,
            demand_number=demand_number,
            approval_cycle_id=cycle.id,
            action_id=None,
            request_version=request.aggregate_version if request is not None else expected_version + 1,
            status=request.status if request is not None else "Soumise",
            quorum=quorum,
            conflict_code="approval_cycle_subject_changed",
            conflict_message=(
                "Le sujet soumis a changé; le cycle a été invalidé et un nouveau cycle est requis."
            ),
        )

    def vote(self, command: ApprovalVoteCommand) -> ApprovalVoteOutcome:
        actor_id = self._actor_id()
        if int(command.expected_request_version) < 1:
            raise ApplicationValidationError(
                "La version attendue de la demande doit être au moins 1.",
                code="demand_version_invalid",
            )
        decision = str(command.decision or "").strip().upper()
        if decision != APPROVAL_DECISION_APPROVE:
            raise ApplicationValidationError(
                "276C supporte uniquement la décision positive APPROVE.",
                code="approval_decision_unsupported",
                context={"decision": decision},
            )

        request = self._cycles.get_request(command.workforce_request_id)
        if request is None:
            raise ApplicationNotFoundError(
                "Demande introuvable.",
                code="demand_not_found",
                context={"workforce_request_id": command.workforce_request_id},
            )
        if request.status != "Soumise":
            raise ApplicationConflictError(
                "La demande n'est pas dans un état votable.",
                code="approval_request_not_submitted",
                context={"status": request.status},
            )

        cycle = self._active_cycle(request.id, command.approval_cycle_id)
        if not self._current_subject_matches(cycle):
            return self._invalidated_outcome(
                cycle=cycle,
                expected_version=int(command.expected_request_version),
                demand_number=request.number,
            )

        targets = self._target_requirements(
            cycle,
            requirement_ids=command.requirement_ids,
            request_line_ids=command.request_line_ids,
        )
        self._assert_actor_eligible(cycle, actor_id, targets)

        existing_decisions = self._repository.list_decisions(cycle.id)
        hypothetical = tuple(existing_decisions) + tuple(
            ApprovalDecisionRecord(
                requirement_id=requirement_id,
                app_user_id=actor_id,
                decision=decision,
                action_id="PENDING",
            )
            for requirement_id in targets
        )
        projected = project_approval_quorum(cycle, hypothetical)
        planning_version: int | None = None
        if projected.complete:
            planning_version = self._planning_versions.acquire(
                command.expected_planning_version
            )

        old_version = int(command.expected_request_version)
        new_version = self._repository.acquire_request_version(
            request.id,
            old_version,
        )

        # Re-read under the request CAS (and, for finalization, the global planning
        # guard). A vote-only aggregate_version increment is deliberately absent from
        # the subject fingerprint.
        cycle = self._active_cycle(request.id, command.approval_cycle_id)
        if not self._current_subject_matches(cycle):
            raise ApplicationConflictError(
                "Le sujet soumis a changé pendant le vote.",
                code="approval_cycle_subject_changed",
                context={"approval_cycle_id": cycle.id},
            )
        targets = self._target_requirements(
            cycle,
            requirement_ids=command.requirement_ids,
            request_line_ids=command.request_line_ids,
        )
        self._assert_actor_eligible(cycle, actor_id, targets)

        action_id = str(uuid4())
        self._repository.append_decisions(
            cycle_id=cycle.id,
            requirement_ids=targets,
            app_user_id=actor_id,
            decision=decision,
            comment=str(command.comment or ""),
            action_id=action_id,
        )
        quorum = project_approval_quorum(
            cycle,
            self._repository.list_decisions(cycle.id),
        )

        if not quorum.complete:
            self._repository.append_vote_audit(
                request_id=request.id,
                cycle_id=cycle.id,
                action_id=action_id,
                requirement_ids=targets,
                old_request_version=old_version,
                new_request_version=new_version,
                quorum=quorum,
            )
            return ApprovalVoteOutcome(
                workforce_request_id=request.id,
                demand_number=request.number,
                approval_cycle_id=cycle.id,
                action_id=action_id,
                request_version=new_version,
                status="Soumise",
                quorum=quorum,
            )

        if planning_version is None:
            # The command was not predicted to finalize, therefore no planning CAS was
            # acquired. Under the request CAS this can only happen if persistence is
            # inconsistent; never materialize outside ADR-006.
            raise ApplicationConflictError(
                "Le quorum a changé sans garde de planning.",
                code="approval_quorum_guard_missing",
                context={"approval_cycle_id": cycle.id},
            )

        self._repository.mark_request_approved(
            request.id,
            actor_name=self._current_user_name,
            comment=str(command.comment or ""),
        )
        self._approved_sync.sync_approved(
            request.number,
            approved_request_version=cycle.submitted_request_version,
        )
        planning = dict(self._planning.rebuild())
        revision_id = self._repository.active_revision_id(request.id)
        if not revision_id:
            raise ApplicationConflictError(
                "La finalisation n'a pas produit de révision approuvée.",
                code="approval_revision_missing",
                context={"approval_cycle_id": cycle.id},
            )
        self._repository.complete_cycle(
            cycle_id=cycle.id,
            approval_revision_id=revision_id,
            action_id=action_id,
            planning_version=planning_version,
        )
        self._repository.append_vote_audit(
            request_id=request.id,
            cycle_id=cycle.id,
            action_id=action_id,
            requirement_ids=targets,
            old_request_version=old_version,
            new_request_version=new_version,
            quorum=quorum,
            planning_version=planning_version,
            approval_revision_id=revision_id,
        )
        return ApprovalVoteOutcome(
            workforce_request_id=request.id,
            demand_number=request.number,
            approval_cycle_id=cycle.id,
            action_id=action_id,
            request_version=new_version,
            status="En planification",
            quorum=quorum,
            approval_revision_id=revision_id,
            planning_version=planning_version,
            planning=planning,
        )

    def approve_all_eligible(
        self,
        *,
        workforce_request_id: str,
        approval_cycle_id: str,
        expected_request_version: int,
        comment: str = "",
        expected_planning_version: int | None = None,
    ) -> ApprovalVoteOutcome:
        actor_id = self._actor_id()
        cycle = self._active_cycle(workforce_request_id, approval_cycle_id)
        eligible = self._eligible_requirements(cycle, actor_id)
        if not eligible:
            raise ApplicationAuthorizationError(
                "L'acteur n'est admissible pour aucune exigence du cycle actif.",
                code="approval_actor_not_eligible",
                context={"app_user_id": actor_id, "approval_cycle_id": cycle.id},
            )
        return self.vote(
            ApprovalVoteCommand(
                workforce_request_id=workforce_request_id,
                approval_cycle_id=approval_cycle_id,
                expected_request_version=expected_request_version,
                requirement_ids=eligible,
                decision=APPROVAL_DECISION_APPROVE,
                comment=comment,
                expected_planning_version=expected_planning_version,
            )
        )
