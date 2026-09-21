from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .errors import (
    ApplicationAuthorizationError,
    ApplicationConflictError,
    ApplicationValidationError,
)
from .read_models import DemandReadModel
from .security import (
    PERMISSION_APPROVE_DEMANDS,
    PERMISSION_MANAGE_DEMANDS,
)


ACTION_MODIFY = "modify"
ACTION_SUBMIT = "submit"
ACTION_APPROVE = "approve"
ACTION_CORRECTION = "correction"
ACTION_CANCEL = "cancel"
ACTION_EMERGENCY_PLAN = "emergency-plan"

DEMAND_WORKFLOW_ACTIONS = (
    ACTION_MODIFY,
    ACTION_SUBMIT,
    ACTION_APPROVE,
    ACTION_CORRECTION,
    ACTION_CANCEL,
    ACTION_EMERGENCY_PLAN,
)


@dataclass(frozen=True, slots=True)
class DemandWorkflowBlock:
    code: str
    message: str
    error_kind: str = "validation"


@dataclass(frozen=True, slots=True)
class DemandWorkflowActionReadModel:
    action: str
    allowed: bool
    required_permission: str
    reason_code: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action,
            "allowed": self.allowed,
            "required_permission": self.required_permission,
            "reason_code": self.reason_code,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class DemandWorkflowReadModel:
    demand_number: str
    status: str
    version: int
    actions: tuple[DemandWorkflowActionReadModel, ...]

    @property
    def available_actions(self) -> tuple[str, ...]:
        return tuple(row.action for row in self.actions if row.allowed)

    def to_dict(self) -> dict[str, object]:
        return {
            "demand_number": self.demand_number,
            "status": self.status,
            "version": self.version,
            "available_actions": list(self.available_actions),
            "actions": [row.to_dict() for row in self.actions],
        }


_ACTION_PERMISSIONS = {
    ACTION_MODIFY: PERMISSION_MANAGE_DEMANDS,
    ACTION_SUBMIT: PERMISSION_MANAGE_DEMANDS,
    ACTION_APPROVE: PERMISSION_APPROVE_DEMANDS,
    ACTION_CORRECTION: PERMISSION_APPROVE_DEMANDS,
    ACTION_CANCEL: PERMISSION_MANAGE_DEMANDS,
    ACTION_EMERGENCY_PLAN: PERMISSION_APPROVE_DEMANDS,
}

_ACTION_STATUSES = {
    ACTION_MODIFY: frozenset({"Brouillon", "À corriger", "Soumise", "En planification"}),
    ACTION_SUBMIT: frozenset({"Brouillon", "À corriger"}),
    ACTION_APPROVE: frozenset({"Soumise"}),
    ACTION_CORRECTION: frozenset({"Soumise"}),
    ACTION_CANCEL: frozenset({"Brouillon", "À corriger", "Soumise", "En planification"}),
    ACTION_EMERGENCY_PLAN: frozenset({"Soumise"}),
}


def _decision(
    demand: DemandReadModel,
    action: str,
    *,
    permissions: Sequence[str],
    business_blocks: Mapping[str, DemandWorkflowBlock] | None = None,
) -> DemandWorkflowActionReadModel:
    required_permission = _ACTION_PERMISSIONS[action]
    if required_permission not in permissions:
        return DemandWorkflowActionReadModel(
            action=action,
            allowed=False,
            required_permission=required_permission,
            reason_code="permission_denied",
            reason="Vous n'avez pas la permission requise pour cette action.",
        )

    if demand.status not in _ACTION_STATUSES[action]:
        return DemandWorkflowActionReadModel(
            action=action,
            allowed=False,
            required_permission=required_permission,
            reason_code="demand_transition_invalid",
            reason=(
                f"L'action {action} n'est pas permise lorsque la demande est "
                f"au statut {demand.status or 'inconnu'}."
            ),
        )

    block = (business_blocks or {}).get(action)
    if block is not None:
        return DemandWorkflowActionReadModel(
            action=action,
            allowed=False,
            required_permission=required_permission,
            reason_code=block.code,
            reason=block.message,
        )

    return DemandWorkflowActionReadModel(
        action=action,
        allowed=True,
        required_permission=required_permission,
    )


def demand_workflow_state(
    demand: DemandReadModel,
    *,
    permissions: Sequence[str],
    business_blocks: Mapping[str, DemandWorkflowBlock] | None = None,
) -> DemandWorkflowReadModel:
    return DemandWorkflowReadModel(
        demand_number=demand.number,
        status=demand.status,
        version=int(demand.version),
        actions=tuple(
            _decision(
                demand,
                action,
                permissions=permissions,
                business_blocks=business_blocks,
            )
            for action in DEMAND_WORKFLOW_ACTIONS
        ),
    )


def assert_demand_action(
    demand: DemandReadModel,
    action: str,
    *,
    permissions: Sequence[str],
    business_blocks: Mapping[str, DemandWorkflowBlock] | None = None,
) -> None:
    if action not in _ACTION_PERMISSIONS:
        raise ApplicationValidationError(
            "Action de workflow inconnue.",
            code="demand_workflow_action_unknown",
            context={"action": action, "demand_number": demand.number},
        )

    decision = _decision(
        demand,
        action,
        permissions=permissions,
        business_blocks=business_blocks,
    )
    if decision.allowed:
        return

    context = {
        "demand_number": demand.number,
        "status": demand.status,
        "version": int(demand.version),
        "action": action,
        "required_permission": decision.required_permission,
    }
    if decision.reason_code == "permission_denied":
        raise ApplicationAuthorizationError(
            decision.reason or "Permission refusée.",
            code="permission_denied",
            context=context,
        )
    if decision.reason_code == "demand_transition_invalid":
        raise ApplicationConflictError(
            decision.reason or "Transition de demande invalide.",
            code="demand_transition_invalid",
            context=context,
        )

    block = (business_blocks or {}).get(action)
    if block is not None and block.error_kind == "conflict":
        raise ApplicationConflictError(
            block.message,
            code=block.code,
            context=context,
        )
    raise ApplicationValidationError(
        decision.reason or "L'action n'est pas permise dans le contexte actuel.",
        code=decision.reason_code or "demand_action_blocked",
        context=context,
    )
