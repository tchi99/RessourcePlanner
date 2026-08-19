from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from typing import Mapping, Sequence


@dataclass(frozen=True)
class Contact:
    person_id: str
    display_name: str
    email: str


@dataclass(frozen=True)
class WeeklyAssignment:
    """One communicated planning line, independent from Excel and email transport."""

    segment_id: str
    resource_id: str
    project_manager_id: str
    project_number: str
    project_name: str
    day: date
    hours: float
    allocation_type: str = "Flexible"
    outside_schedule: bool = False
    confirmation: str = "Confirmée"


@dataclass(frozen=True)
class AssignmentChange:
    segment_id: str
    kind: str  # added | removed | modified
    before: tuple[WeeklyAssignment, ...] = ()
    after: tuple[WeeklyAssignment, ...] = ()


@dataclass(frozen=True)
class CommunicationDraft:
    audience: str  # technician | project_manager
    recipient_id: str
    recipient_email: str
    subject: str
    body: str
    message_kind: str  # weekly_plan | planning_change
    week_start: date
    snapshot_fingerprint: str
    requires_manual_approval: bool = True


@dataclass(frozen=True)
class CommunicationBatch:
    drafts: tuple[CommunicationDraft, ...]
    missing_contact_ids: tuple[str, ...]
    snapshot_fingerprint: str


def _rounded_hours(value: float) -> float:
    return round(max(float(value), 0.0), 2)


def _assignment_payload(row: WeeklyAssignment) -> tuple[object, ...]:
    return (
        row.segment_id,
        row.resource_id,
        row.project_manager_id,
        row.project_number,
        row.project_name,
        row.day.isoformat(),
        _rounded_hours(row.hours),
        row.allocation_type,
        bool(row.outside_schedule),
        row.confirmation,
    )


def snapshot_fingerprint(assignments: Sequence[WeeklyAssignment]) -> str:
    payload = sorted(_assignment_payload(row) for row in assignments)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _line(row: WeeklyAssignment, *, include_resource: bool) -> str:
    project = " — ".join(part for part in [row.project_number, row.project_name] if part) or "Projet non précisé"
    extras: list[str] = [row.allocation_type]
    if row.confirmation:
        extras.append(row.confirmation)
    if row.outside_schedule:
        extras.append("hors horaire")
    resource = f" · {row.resource_id}" if include_resource else ""
    return f"- {row.day.isoformat()} · {row.hours:g} h{resource} · {project} · {' · '.join(extras)}"


def _contact(
    contacts: Mapping[str, Contact],
    person_id: str,
    missing: set[str],
) -> Contact | None:
    contact = contacts.get(person_id)
    if contact is None or not str(contact.email or "").strip():
        if person_id:
            missing.add(person_id)
        return None
    return contact


def build_weekly_plan_batch(
    assignments: Sequence[WeeklyAssignment],
    contacts: Mapping[str, Contact],
    week_start: date,
) -> CommunicationBatch:
    """Prepare weekly emails only; this function can never send them.

    One personalized draft is created per technician and per project manager. Contacts
    must be explicit; addresses are never inferred from names.
    """
    rows = sorted(assignments, key=lambda row: (row.day, row.project_number, row.segment_id))
    fingerprint = snapshot_fingerprint(rows)
    missing: set[str] = set()
    drafts: list[CommunicationDraft] = []

    resource_ids = sorted({row.resource_id for row in rows if row.resource_id})
    for resource_id in resource_ids:
        contact = _contact(contacts, resource_id, missing)
        if not contact:
            continue
        own = [row for row in rows if row.resource_id == resource_id]
        body = (
            f"Bonjour {contact.display_name},\n\n"
            f"Voici tes attributions prévues pour la semaine du {week_start.isoformat()} :\n\n"
            + "\n".join(_line(row, include_resource=False) for row in own)
            + "\n\nMerci de communiquer avec le coordonnateur si un élément doit être clarifié."
        )
        drafts.append(
            CommunicationDraft(
                audience="technician",
                recipient_id=resource_id,
                recipient_email=contact.email,
                subject=f"Planification — semaine du {week_start.isoformat()}",
                body=body,
                message_kind="weekly_plan",
                week_start=week_start,
                snapshot_fingerprint=fingerprint,
            )
        )

    manager_ids = sorted({row.project_manager_id for row in rows if row.project_manager_id})
    for manager_id in manager_ids:
        contact = _contact(contacts, manager_id, missing)
        if not contact:
            continue
        own = [row for row in rows if row.project_manager_id == manager_id]
        body = (
            f"Bonjour {contact.display_name},\n\n"
            f"Voici la main-d'œuvre planifiée sous ta responsabilité pour la semaine du {week_start.isoformat()} :\n\n"
            + "\n".join(_line(row, include_resource=True) for row in own)
            + "\n\nMerci de communiquer avec le coordonnateur si un élément doit être clarifié."
        )
        drafts.append(
            CommunicationDraft(
                audience="project_manager",
                recipient_id=manager_id,
                recipient_email=contact.email,
                subject=f"Main-d'œuvre planifiée — semaine du {week_start.isoformat()}",
                body=body,
                message_kind="weekly_plan",
                week_start=week_start,
                snapshot_fingerprint=fingerprint,
            )
        )

    drafts.sort(key=lambda row: (row.audience, row.recipient_id))
    return CommunicationBatch(tuple(drafts), tuple(sorted(missing)), fingerprint)


def _group_by_segment(assignments: Sequence[WeeklyAssignment]) -> dict[str, tuple[WeeklyAssignment, ...]]:
    result: dict[str, list[WeeklyAssignment]] = {}
    for row in assignments:
        result.setdefault(row.segment_id, []).append(row)
    return {
        segment_id: tuple(sorted(rows, key=lambda row: (row.day, row.resource_id, row.hours)))
        for segment_id, rows in result.items()
    }


def compare_weekly_assignments(
    previous: Sequence[WeeklyAssignment],
    current: Sequence[WeeklyAssignment],
) -> tuple[AssignmentChange, ...]:
    before = _group_by_segment(previous)
    after = _group_by_segment(current)
    changes: list[AssignmentChange] = []
    for segment_id in sorted(set(before) | set(after)):
        old = before.get(segment_id, ())
        new = after.get(segment_id, ())
        if not old:
            changes.append(AssignmentChange(segment_id, "added", (), new))
        elif not new:
            changes.append(AssignmentChange(segment_id, "removed", old, ()))
        elif tuple(_assignment_payload(row) for row in old) != tuple(_assignment_payload(row) for row in new):
            changes.append(AssignmentChange(segment_id, "modified", old, new))
    return tuple(changes)


def _change_lines(change: AssignmentChange, recipient_id: str, audience: str) -> list[str]:
    lines: list[str] = []
    label = {"added": "AJOUT", "removed": "ANNULATION", "modified": "MODIFICATION"}[change.kind]
    relevant_before = [
        row for row in change.before
        if (audience == "technician" and row.resource_id == recipient_id)
        or (audience == "project_manager" and row.project_manager_id == recipient_id)
    ]
    relevant_after = [
        row for row in change.after
        if (audience == "technician" and row.resource_id == recipient_id)
        or (audience == "project_manager" and row.project_manager_id == recipient_id)
    ]
    if relevant_before:
        lines.append(f"{label} — avant :")
        lines.extend(_line(row, include_resource=audience == "project_manager") for row in relevant_before)
    if relevant_after:
        lines.append(f"{label} — maintenant :")
        lines.extend(_line(row, include_resource=audience == "project_manager") for row in relevant_after)
    return lines


def build_change_notification_batch(
    previous: Sequence[WeeklyAssignment],
    current: Sequence[WeeklyAssignment],
    contacts: Mapping[str, Contact],
    week_start: date,
) -> CommunicationBatch:
    """Prepare only notifications affected by changes since the communicated snapshot."""
    changes = compare_weekly_assignments(previous, current)
    fingerprint = snapshot_fingerprint(current)
    missing: set[str] = set()
    drafts: list[CommunicationDraft] = []

    impacted_technicians: set[str] = set()
    impacted_managers: set[str] = set()
    for change in changes:
        impacted_technicians.update(row.resource_id for row in change.before + change.after if row.resource_id)
        impacted_managers.update(row.project_manager_id for row in change.before + change.after if row.project_manager_id)

    for audience, recipient_ids in (
        ("technician", sorted(impacted_technicians)),
        ("project_manager", sorted(impacted_managers)),
    ):
        for recipient_id in recipient_ids:
            lines: list[str] = []
            for change in changes:
                lines.extend(_change_lines(change, recipient_id, audience))
            if not lines:
                continue
            contact = _contact(contacts, recipient_id, missing)
            if not contact:
                continue
            body = (
                f"Bonjour {contact.display_name},\n\n"
                f"Le planning déjà communiqué pour la semaine du {week_start.isoformat()} a été modifié. "
                "Voici les changements qui te concernent :\n\n"
                + "\n".join(lines)
                + "\n\nCette communication a été préparée à la suite d'une modification du planning."
            )
            drafts.append(
                CommunicationDraft(
                    audience=audience,
                    recipient_id=recipient_id,
                    recipient_email=contact.email,
                    subject=f"Modification de planification — semaine du {week_start.isoformat()}",
                    body=body,
                    message_kind="planning_change",
                    week_start=week_start,
                    snapshot_fingerprint=fingerprint,
                )
            )

    drafts.sort(key=lambda row: (row.audience, row.recipient_id))
    return CommunicationBatch(tuple(drafts), tuple(sorted(missing)), fingerprint)
