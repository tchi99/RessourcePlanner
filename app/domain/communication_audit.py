from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Sequence


STATUS_PREPARED = "Préparé"
STATUS_APPROVED = "Approuvé"
STATUS_DRAFTS_CREATED = "Brouillons créés"
STATUS_COMMUNICATED = "Communiqué"
STATUS_CANCELLED = "Annulé"
STATUS_OBSOLETE = "Obsolète"
VALID_STATUSES = {
    STATUS_PREPARED,
    STATUS_APPROVED,
    STATUS_DRAFTS_CREATED,
    STATUS_COMMUNICATED,
    STATUS_CANCELLED,
    STATUS_OBSOLETE,
}


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


def mark_drafts_created(state: CommunicationAuditState) -> CommunicationAuditState:
    if state.status == STATUS_DRAFTS_CREATED:
        return state
    if state.status != STATUS_APPROVED:
        raise ValueError("Le lot doit être approuvé avant de créer les brouillons Outlook.")
    return CommunicationAuditState(
        batch_id=state.batch_id,
        week_start=state.week_start,
        message_kind=state.message_kind,
        snapshot_fingerprint=state.snapshot_fingerprint,
        status=STATUS_DRAFTS_CREATED,
        prepared_by=state.prepared_by,
        prepared_at=state.prepared_at,
        approved_by=state.approved_by,
        approved_at=state.approved_at,
        communicated_at=state.communicated_at,
    )


def mark_communicated(
    state: CommunicationAuditState,
    *,
    communicated_at: datetime,
) -> CommunicationAuditState:
    if state.status not in {STATUS_APPROVED, STATUS_DRAFTS_CREATED}:
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


def mark_obsolete(state: CommunicationAuditState) -> CommunicationAuditState:
    """Invalidate an unsent batch after the planning snapshot changed."""
    if state.status == STATUS_OBSOLETE:
        return state
    if state.status not in {STATUS_PREPARED, STATUS_APPROVED, STATUS_DRAFTS_CREATED}:
        raise ValueError(
            "Seul un lot préparé, approuvé ou dont les brouillons ont été créés peut devenir obsolète."
        )
    return CommunicationAuditState(
        batch_id=state.batch_id,
        week_start=state.week_start,
        message_kind=state.message_kind,
        snapshot_fingerprint=state.snapshot_fingerprint,
        status=STATUS_OBSOLETE,
        prepared_by=state.prepared_by,
        prepared_at=state.prepared_at,
        approved_by=state.approved_by,
        approved_at=state.approved_at,
        communicated_at=state.communicated_at,
    )


def is_stale_open_batch(
    status: str,
    stored_fingerprint: str,
    current_fingerprint: str,
) -> bool:
    """Return True for stale batches that have not yet created Outlook drafts.

    Once drafts exist, a planning change requires an explicit coordinator decision:
    either the drafts were already sent and the old snapshot must be marked communicated,
    or they were not sent and the coordinator can explicitly obsolete the batch.
    """
    return (
        str(status or "") in {STATUS_PREPARED, STATUS_APPROVED}
        and bool(str(stored_fingerprint or "").strip())
        and str(stored_fingerprint or "") != str(current_fingerprint or "")
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
