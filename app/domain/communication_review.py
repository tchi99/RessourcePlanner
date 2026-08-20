from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .communication_planning import CommunicationBatch, CommunicationDraft


DraftKey = tuple[str, str]


@dataclass(frozen=True)
class DraftReview:
    include: bool = True
    subject: str | None = None
    body: str | None = None


def draft_key(draft: CommunicationDraft) -> DraftKey:
    return draft.audience, draft.recipient_id


def apply_manual_review(
    batch: CommunicationBatch,
    reviews: Mapping[DraftKey, DraftReview],
) -> CommunicationBatch:
    """Apply coordinator edits/exclusions without changing the planning fingerprint."""
    drafts: list[CommunicationDraft] = []
    for draft in batch.drafts:
        review = reviews.get(draft_key(draft), DraftReview())
        if not review.include:
            continue
        subject = draft.subject if review.subject is None else str(review.subject).strip()
        body = draft.body if review.body is None else str(review.body).strip()
        if not subject:
            raise ValueError("L'objet d'un message inclus ne peut pas être vide.")
        if not body:
            raise ValueError("Le corps d'un message inclus ne peut pas être vide.")
        drafts.append(
            CommunicationDraft(
                audience=draft.audience,
                recipient_id=draft.recipient_id,
                recipient_email=draft.recipient_email,
                subject=subject,
                body=body,
                message_kind=draft.message_kind,
                week_start=draft.week_start,
                snapshot_fingerprint=draft.snapshot_fingerprint,
                requires_manual_approval=True,
            )
        )
    return CommunicationBatch(
        drafts=tuple(drafts),
        missing_contact_ids=batch.missing_contact_ids,
        snapshot_fingerprint=batch.snapshot_fingerprint,
    )


def stale_prepared_batch(
    prepared_fingerprint: str,
    current_fingerprint: str,
) -> bool:
    prepared = str(prepared_fingerprint or "").strip()
    current = str(current_fingerprint or "").strip()
    return bool(prepared and current and prepared != current)


def reviewed_recipient_count(
    drafts: Sequence[CommunicationDraft],
) -> int:
    return len({draft_key(draft) for draft in drafts})
