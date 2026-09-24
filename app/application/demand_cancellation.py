from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .query_models import DemandCancellationMaterializationReadModel
from .read_models import DemandReadModel
from .security import (
    PERMISSION_APPROVE_DEMANDS,
    PERMISSION_MANAGE_DEMANDS,
    PERMISSION_MANAGE_PLANNING,
)


CANCELLATION_STATE_PENDING = "PENDING"
CANCELLATION_STATE_REJECTED = "REJECTED"
CANCELLATION_STATE_ACCEPTED = "ACCEPTED"

CANCELLABLE_STATUSES = frozenset(
    {"Brouillon", "À corriger", "Soumise", "En planification"}
)


@dataclass(frozen=True, slots=True)
class DemandCancellationPolicyReadModel:
    has_operational_decisions: bool
    direct_cancel: bool
    request_cancellation: bool
    cancellation_pending: bool
    resolve_cancellation: bool
    reason_code: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "has_operational_decisions": self.has_operational_decisions,
            "direct_cancel": self.direct_cancel,
            "request_cancellation": self.request_cancellation,
            "cancellation_pending": self.cancellation_pending,
            "resolve_cancellation": self.resolve_cancellation,
            "reason_code": self.reason_code,
            "reason": self.reason,
        }


def demand_cancellation_policy(
    demand: DemandReadModel,
    *,
    permissions: Sequence[str],
    materialization: DemandCancellationMaterializationReadModel | None = None,
) -> DemandCancellationPolicyReadModel:
    """Return the single authoritative cancellation policy for one actor.

    The primary demand status remains unchanged while a cancellation request is
    pending. Operational materialization is authoritative: a Shift or an
    AssetAllocation requires the explicit request/resolution workflow, while
    requirements without a concrete decision can still be cancelled directly.
    """

    state = str(demand.cancellation_state or "").strip().upper() or None
    pending = state == CANCELLATION_STATE_PENDING
    has_operational_decisions = bool(
        materialization is not None and materialization.has_operational_decisions
    )
    can_manage = PERMISSION_MANAGE_DEMANDS in permissions
    can_resolve = (
        PERMISSION_APPROVE_DEMANDS in permissions
        and PERMISSION_MANAGE_PLANNING in permissions
    )

    if demand.status not in CANCELLABLE_STATUSES:
        return DemandCancellationPolicyReadModel(
            has_operational_decisions=has_operational_decisions,
            direct_cancel=False,
            request_cancellation=False,
            cancellation_pending=pending,
            resolve_cancellation=False,
            reason_code="demand_transition_invalid",
            reason=(
                "L'annulation n'est pas permise lorsque la demande est "
                f"au statut {demand.status or 'inconnu'}."
            ),
        )

    if pending:
        return DemandCancellationPolicyReadModel(
            has_operational_decisions=has_operational_decisions,
            direct_cancel=False,
            request_cancellation=False,
            cancellation_pending=True,
            resolve_cancellation=can_resolve,
            reason_code="cancellation_pending",
            reason="Une demande d'annulation est déjà en attente de traitement.",
        )

    if has_operational_decisions:
        return DemandCancellationPolicyReadModel(
            has_operational_decisions=True,
            direct_cancel=False,
            request_cancellation=can_manage,
            cancellation_pending=False,
            resolve_cancellation=False,
            reason_code="active_operational_decisions",
            reason="La demande contient des décisions opérationnelles actives.",
        )

    if not can_manage:
        return DemandCancellationPolicyReadModel(
            has_operational_decisions=False,
            direct_cancel=False,
            request_cancellation=False,
            cancellation_pending=False,
            resolve_cancellation=False,
            reason_code="permission_denied",
            reason="Vous n'avez pas la permission requise pour annuler cette demande.",
        )

    return DemandCancellationPolicyReadModel(
        has_operational_decisions=False,
        direct_cancel=True,
        request_cancellation=False,
        cancellation_pending=False,
        resolve_cancellation=False,
    )
