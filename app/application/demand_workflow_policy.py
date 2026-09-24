from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .demand_cancellation import (
    DemandCancellationPolicyReadModel,
    demand_cancellation_policy,
)
from .errors import (
    ApplicationAuthorizationError,
    ApplicationConflictError,
    ApplicationValidationError,
)
from .query_models import DemandCancellationMaterializationReadModel
from .read_models import DemandReadModel
from .security import (
    PERMISSION_APPROVE_DEMANDS,
    PERMISSION_MANAGE_DEMANDS,
    PERMISSION_MANAGE_PLANNING,
)


ACTION_MODIFY = "modify"
ACTION_SUBMIT = "submit"
ACTION_APPROVE = "approve"
ACTION_CORRECTION = "correction"
ACTION_CANCEL = "cancel"
ACTION_REQUEST_CANCELLATION = "request-cancellation"
ACTION_REJECT_CANCELLATION = "reject-cancellation"
ACTION_EMERGENCY_PLAN = "emergency-plan"

DEMAND_WORKFLOW_ACTIONS = (
    ACTION_MODIFY,
    ACTION_SUBMIT,
    ACTION_APPROVE,
    ACTION_CORRECTION,
    ACTION_CANCEL,
    ACTION_REQUEST_CANCELLATION,
    ACTION_REJECT_CANCELLATION,
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
    required_permissions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action,
            "allowed": self.allowed,
            "required_permission": self.required_permission,
            "required_permissions": list(
                self.required_permissions or (self.required_permission,)
            ),
            "reason_code": self.reason_code,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class DemandWorkflowReadModel:
    demand_number: str
    status: str
    version: int
    actions: tuple[DemandWorkflowActionReadModel, ...]
    cancellation: DemandCancellationPolicyReadModel | None = None

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
            "cancellation": (
                self.cancellation.to_dict() if self.cancellation is not None else None
            ),
        }


_ACTION_PERMISSIONS = {
    ACTION_MODIFY: (PERMISSION_MANAGE_DEMANDS,),
    ACTION_SUBMIT: (PERMISSION_MANAGE_DEMANDS,),
    ACTION_APPROVE: (PERMISSION_APPROVE_DEMANDS,),
    ACTION_CORRECTION: (PERMISSION_APPROVE_DEMANDS,),
    ACTION_CANCEL: (PERMISSION_MANAGE_DEMANDS,),
    ACTION_REQUEST_CANCELLATION: (PERMISSION_MANAGE_DEMANDS,),
    ACTION_REJECT_CANCELLATION: (
        PERMISSION_APPROVE_DEMANDS,
        PERMISSION_MANAGE_PLANNING,
    ),
    ACTION_EMERGENCY_PLAN: (PERMISSION_APPROVE_DEMANDS,),
}

_ACTION_STATUSES = {
    ACTION_MODIFY: frozenset({"Brouillon", "À corriger", "Soumise", "En planification"}),
    ACTION_SUBMIT: frozenset({"Brouillon", "À corriger"}),
    ACTION_APPROVE: frozenset({"Soumise"}),
    ACTION_CORRECTION: frozenset({"Soumise"}),
    ACTION_CANCEL: frozenset({"Brouillon", "À corriger", "Soumise", "En planification"}),
    ACTION_REQUEST_CANCELLATION: frozenset(
        {"Brouillon", "À corriger", "Soumise", "En planification"}
    ),
    ACTION_REJECT_CANCELLATION: frozenset(
        {"Brouillon", "À corriger", "Soumise", "En planification"}
    ),
    ACTION_EMERGENCY_PLAN: frozenset({"Soumise"}),
}


def _cancellation_blocks(
    policy: DemandCancellationPolicyReadModel,
) -> dict[str, DemandWorkflowBlock]:
    blocks: dict[str, DemandWorkflowBlock] = {}
    if not policy.direct_cancel:
        blocks[ACTION_CANCEL] = DemandWorkflowBlock(
            code=policy.reason_code or "direct_cancellation_unavailable",
            message=policy.reason or "L'annulation directe n'est pas disponible.",
            error_kind="conflict",
        )

    if not policy.request_cancellation:
        if policy.cancellation_pending:
            code = "cancellation_pending"
            message = "Une demande d'annulation est déjà en attente de traitement."
        elif not policy.has_operational_decisions:
            code = "cancellation_request_not_required"
            message = (
                "Aucune décision opérationnelle active ne nécessite une demande "
                "d'annulation."
            )
        else:
            code = policy.reason_code or "cancellation_request_unavailable"
            message = policy.reason or "La demande d'annulation n'est pas disponible."
        blocks[ACTION_REQUEST_CANCELLATION] = DemandWorkflowBlock(
            code=code,
            message=message,
            error_kind="conflict",
        )

    if not policy.cancellation_pending:
        blocks[ACTION_REJECT_CANCELLATION] = DemandWorkflowBlock(
            code="cancellation_not_pending",
            message="Aucune demande d'annulation n'est en attente.",
            error_kind="conflict",
        )
    return blocks


def _decision(
    demand: DemandReadModel,
    action: str,
    *,
    permissions: Sequence[str],
    business_blocks: Mapping[str, DemandWorkflowBlock] | None = None,
) -> DemandWorkflowActionReadModel:
    required_permissions = _ACTION_PERMISSIONS[action]
    required_permission = required_permissions[0]
    missing_permissions = tuple(
        permission for permission in required_permissions if permission not in permissions
    )
    if missing_permissions:
        return DemandWorkflowActionReadModel(
            action=action,
            allowed=False,
            required_permission=required_permission,
            required_permissions=required_permissions,
            reason_code="permission_denied",
            reason="Vous n'avez pas la permission requise pour cette action.",
        )

    if demand.status not in _ACTION_STATUSES[action]:
        return DemandWorkflowActionReadModel(
            action=action,
            allowed=False,
            required_permission=required_permission,
            required_permissions=required_permissions,
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
            required_permissions=required_permissions,
            reason_code=block.code,
            reason=block.message,
        )

    return DemandWorkflowActionReadModel(
        action=action,
        allowed=True,
        required_permission=required_permission,
        required_permissions=required_permissions,
    )


def demand_workflow_state(
    demand: DemandReadModel,
    *,
    permissions: Sequence[str],
    business_blocks: Mapping[str, DemandWorkflowBlock] | None = None,
    materialization: DemandCancellationMaterializationReadModel | None = None,
) -> DemandWorkflowReadModel:
    cancellation = demand_cancellation_policy(
        demand,
        permissions=permissions,
        materialization=materialization,
    )
    blocks = dict(business_blocks or {})
    for action, block in _cancellation_blocks(cancellation).items():
        blocks.setdefault(action, block)

    return DemandWorkflowReadModel(
        demand_number=demand.number,
        status=demand.status,
        version=int(demand.version),
        actions=tuple(
            _decision(
                demand,
                action,
                permissions=permissions,
                business_blocks=blocks,
            )
            for action in DEMAND_WORKFLOW_ACTIONS
        ),
        cancellation=cancellation,
    )


def assert_demand_action(
    demand: DemandReadModel,
    action: str,
    *,
    permissions: Sequence[str],
    business_blocks: Mapping[str, DemandWorkflowBlock] | None = None,
    materialization: DemandCancellationMaterializationReadModel | None = None,
) -> None:
    if action not in _ACTION_PERMISSIONS:
        raise ApplicationValidationError(
            "Action de workflow inconnue.",
            code="demand_workflow_action_unknown",
            context={"action": action, "demand_number": demand.number},
        )

    cancellation = demand_cancellation_policy(
        demand,
        permissions=permissions,
        materialization=materialization,
    )
    blocks = dict(business_blocks or {})
    for candidate_action, block in _cancellation_blocks(cancellation).items():
        blocks.setdefault(candidate_action, block)

    decision = _decision(
        demand,
        action,
        permissions=permissions,
        business_blocks=blocks,
    )
    if decision.allowed:
        return

    context = {
        "demand_number": demand.number,
        "status": demand.status,
        "version": int(demand.version),
        "action": action,
        "required_permission": decision.required_permission,
        "required_permissions": list(
            decision.required_permissions or (decision.required_permission,)
        ),
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

    block = blocks.get(action)
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
