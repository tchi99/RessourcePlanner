from __future__ import annotations

from typing import Any, Mapping, Sequence

from .communication_audit import STATUS_APPROVED


MESSAGE_STATUS_DRAFT_CREATED = "Brouillon créé"


def pending_draft_message_ids(messages: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    """Return approved message IDs that still need an Outlook draft."""
    result: list[str] = []
    for row in messages:
        if str(row.get("Statut") or "") != STATUS_APPROVED:
            continue
        message_id = str(row.get("IDMessage") or "").strip()
        if message_id:
            result.append(message_id)
    return tuple(result)


def draft_created_message_ids(messages: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    result: list[str] = []
    for row in messages:
        if str(row.get("Statut") or "") != MESSAGE_STATUS_DRAFT_CREATED:
            continue
        message_id = str(row.get("IDMessage") or "").strip()
        if message_id:
            result.append(message_id)
    return tuple(result)


def all_message_drafts_created(messages: Sequence[Mapping[str, Any]]) -> bool:
    """A communicated batch must have at least one message and every draft created."""
    rows = [row for row in messages if str(row.get("IDMessage") or "").strip()]
    return bool(rows) and all(
        str(row.get("Statut") or "") == MESSAGE_STATUS_DRAFT_CREATED
        for row in rows
    )
