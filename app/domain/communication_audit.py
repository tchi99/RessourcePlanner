from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Sequence


STATUS_PREPARED = "Préparé"
STATUS_APPROVED = "Approuvé"
STATUS_COMMUNICATED = "Communiqué"
STATUS_CANCELLED = "Annulé"
VALID_STATUSES = {STATUS_PREPARED, STATUS_APPROVED, STATUS_COMMUNICATED, STATUS_CANCELLED}


@dataclass(frozen=True)
class CommunicationAuditState:
    batch_id: str
    week_start: date
    message_kind: str
    snapshot_fingerprint: str
    status: str = STATUS_PREPARED
    prepared_by: str = ""
    prepared_at: datetime | None = None
    approved_by: str = ""
    approved_at: datetime | None = None
    communicated_at: datetime | None = None


def approve_batch(
    state: CommunicationAuditState,
    *,
    approved_by: str,
    approved_at: datetime,
) -> CommunicationAuditState:
    if state.status != STATUS_PREPARED:
        raise ValueError("Seul un lot préparé peut être approuvé.")
    if not str(approved_by or "").strip():
        raise ValueError("Le coordonnateur qui approuve le lot est requis.")
    return CommunicationAuditState(
        batch_id=state.batch_id,
        week_start=state.week_start,
        message_kind=state.message_kind,
        snapshot_fingerprint=state.snapshot_fingerprint,
        status=STATUS_APPROVED,
        prepared_by=state.prepared_by,
        prepared_at=state.prepared_at,
        approved_by=str(approved_by).strip(),
        approved_at=approved_at,
        communicated_at=state.communicated_at,
    )


def mark_communicated(
    state: CommunicationAuditState,
    *,
    communicated_at: datetime,
) -> CommunicationAuditState:
    if state.status != STATUS_APPROVED:
        raise ValueError("Un lot doit être approuvé avant d'être marqué communiqué.")
    return CommunicationAuditState(
        batch_id=state.batch_id,
        week_start=state.week_start,
        message_kind=state.message_kind,
        snapshot_fingerprint=state.snapshot_fingerprint,
        status=STATUS_COMMUNICATED,
        prepared_by=state.prepared_by,
        prepared_at=state.prepared_at,
        approved_by=state.approved_by,
        approved_at=state.approved_at,
        communicated_at=communicated_at,
    )


def cancel_batch(state: CommunicationAuditState) -> CommunicationAuditState:
    if state.status == STATUS_COMMUNICATED:
        raise ValueError("Un lot déjà communiqué ne peut pas être annulé rétroactivement.")
    if state.status == STATUS_CANCELLED:
        return state
    return CommunicationAuditState(
        batch_id=state.batch_id,
        week_start=state.week_start,
        message_kind=state.message_kind,
        snapshot_fingerprint=state.snapshot_fingerprint,
        status=STATUS_CANCELLED,
        prepared_by=state.prepared_by,
        prepared_at=state.prepared_at,
        approved_by=state.approved_by,
        approved_at=state.approved_at,
        communicated_at=state.communicated_at,
    )


def is_duplicate_communicated_snapshot(
    fingerprint: str,
    communicated_states: Sequence[CommunicationAuditState],
    *,
    week_start: date,
    message_kind: str = "weekly_plan",
) -> bool:
    candidate = str(fingerprint or "").strip()
    if not candidate:
        return False
    return any(
        row.status == STATUS_COMMUNICATED
        and row.week_start == week_start
        and row.message_kind == message_kind
        and row.snapshot_fingerprint == candidate
        for row in communicated_states
    )
