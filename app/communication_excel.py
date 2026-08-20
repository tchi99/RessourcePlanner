from __future__ import annotations

from datetime import date, datetime
from typing import Any, Sequence
from uuid import uuid4

from .domain.communication_audit import (
    CommunicationAuditState,
    STATUS_APPROVED,
    STATUS_COMMUNICATED,
    STATUS_OBSOLETE,
    STATUS_PREPARED,
    approve_batch,
    is_stale_open_batch,
    mark_communicated,
    mark_obsolete,
)
from .domain.communication_planning import CommunicationBatch, Contact, WeeklyAssignment
from .excel_repository import ExcelRepository, MASTER_SHEETS, _as_matrix, _date_from_any


CONTACT_SHEET = "ContactsMO"
CONTACT_TABLE = "ContactsMOTable"
CONTACT_HEADERS = ["PersonneCle", "TypePersonne", "NomAffiche", "Courriel", "Actif", "DateModification"]

BATCH_SHEET = "CommunicationLotsMO"
BATCH_TABLE = "CommunicationLotsMOTable"
BATCH_HEADERS = [
    "IDLot",
    "SemaineDebut",
    "TypeCommunication",
    "EmpreintePlanning",
    "Statut",
    "PreparePar",
    "DatePreparation",
    "ApprouvePar",
    "DateApprobation",
    "DateCommunication",
]

MESSAGE_SHEET = "CommunicationMessagesMO"
MESSAGE_TABLE = "CommunicationMessagesMOTable"
MESSAGE_HEADERS = [
    "IDMessage",
    "IDLot",
    "Audience",
    "DestinataireCle",
    "Courriel",
    "Objet",
    "Corps",
    "Statut",
]

SNAPSHOT_SHEET = "CommunicationSnapshotMO"
SNAPSHOT_TABLE = "CommunicationSnapshotMOTable"
SNAPSHOT_HEADERS = [
    "IDLot",
    "SemaineDebut",
    "IDSegment",
    "RessourceCle",
    "NomRessource",
    "ChargeProjetCle",
    "NumeroProjet",
    "NomProjet",
    "Date",
    "Heures",
    "TypeAllocation",
    "HorsHoraire",
    "Confirmation",
]

TRUE_VALUES = {"oui", "true", "1", "x", "yes", "actif", "active"}


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in TRUE_VALUES


def ensure_communication_sheets(repo: ExcelRepository) -> None:
    """Create the communication registry without enabling any email transport."""
    with repo._lock:
        MASTER_SHEETS.add(CONTACT_SHEET)
        repo._ensure_sheet_table(CONTACT_SHEET, CONTACT_HEADERS, CONTACT_TABLE)
        repo._ensure_sheet_table(BATCH_SHEET, BATCH_HEADERS, BATCH_TABLE)
        repo._ensure_sheet_table(MESSAGE_SHEET, MESSAGE_HEADERS, MESSAGE_TABLE)
        repo._ensure_sheet_table(SNAPSHOT_SHEET, SNAPSHOT_HEADERS, SNAPSHOT_TABLE)
        repo.save()


def contacts_by_id(repo: ExcelRepository) -> dict[str, Contact]:
    ensure_communication_sheets(repo)
    rows = repo._sheet_as_records(CONTACT_SHEET, "PersonneCle")
    result: dict[str, Contact] = {}
    for row in rows:
        person_id = str(row.get("PersonneCle") or "").strip()
        email = str(row.get("Courriel") or "").strip()
        if not person_id or not email or not _truthy(row.get("Actif") if row.get("Actif") not in (None, "") else "Oui"):
            continue
        result[person_id] = Contact(
            person_id=person_id,
            display_name=str(row.get("NomAffiche") or person_id).strip(),
            email=email,
        )
    return result


def _append_rows(repo: ExcelRepository, sheet_name: str, table_name: str, headers: list[str], rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        return
    sheet = repo._book().sheets[sheet_name]
    last = max(int(sheet.used_range.last_cell.row), 1)
    start = last + 1
    matrix = [[row.get(header) for header in headers] for row in rows]
    sheet.range((start, 1), (start + len(matrix) - 1, len(headers))).value = matrix
    try:
        table = sheet.tables[table_name]
        table.resize(sheet.range((1, 1), (start + len(matrix) - 1, len(headers))))
    except Exception:
        pass


def _batch_state_from_row(row: dict[str, Any]) -> CommunicationAuditState:
    return CommunicationAuditState(
        batch_id=str(row.get("IDLot") or ""),
        week_start=_date_from_any(row.get("SemaineDebut")) or date.min,
        message_kind=str(row.get("TypeCommunication") or ""),
        snapshot_fingerprint=str(row.get("EmpreintePlanning") or ""),
        status=str(row.get("Statut") or STATUS_PREPARED),
        prepared_by=str(row.get("PreparePar") or ""),
        prepared_at=row.get("DatePreparation") if isinstance(row.get("DatePreparation"), datetime) else None,
        approved_by=str(row.get("ApprouvePar") or ""),
        approved_at=row.get("DateApprobation") if isinstance(row.get("DateApprobation"), datetime) else None,
        communicated_at=row.get("DateCommunication") if isinstance(row.get("DateCommunication"), datetime) else None,
    )


def _locate_batch_row(repo: ExcelRepository, batch_id: str) -> int:
    sheet = repo._book().sheets[BATCH_SHEET]
    matrix = _as_matrix(sheet.used_range.value)
    for offset, row in enumerate(matrix[1:], start=2):
        if row and str(row[0] or "") == str(batch_id):
            return offset
    raise KeyError(f"Lot de communication introuvable: {batch_id}")


def _batch_record(repo: ExcelRepository, batch_id: str) -> dict[str, Any]:
    for row in repo._sheet_as_records(BATCH_SHEET, "IDLot"):
        if str(row.get("IDLot") or "") == str(batch_id):
            return row
    raise KeyError(f"Lot de communication introuvable: {batch_id}")


def persist_prepared_batch(
    repo: ExcelRepository,
    batch: CommunicationBatch,
    assignments: Sequence[WeeklyAssignment],
    *,
    week_start: date,
    message_kind: str,
    prepared_by: str,
    prepared_at: datetime | None = None,
) -> str:
    """Persist a reviewable outbox. This function never approves or sends anything."""
    ensure_communication_sheets(repo)
    prepared_at = prepared_at or datetime.now()
    batch_id = f"COM-{prepared_at.strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"

    batch_row = {
        "IDLot": batch_id,
        "SemaineDebut": datetime.combine(week_start, datetime.min.time()),
        "TypeCommunication": message_kind,
        "EmpreintePlanning": batch.snapshot_fingerprint,
        "Statut": STATUS_PREPARED,
        "PreparePar": str(prepared_by or ""),
        "DatePreparation": prepared_at,
        "ApprouvePar": "",
        "DateApprobation": None,
        "DateCommunication": None,
    }
    message_rows = [
        {
            "IDMessage": f"MSG-{batch_id}-{index:03d}",
            "IDLot": batch_id,
            "Audience": draft.audience,
            "DestinataireCle": draft.recipient_id,
            "Courriel": draft.recipient_email,
            "Objet": draft.subject,
            "Corps": draft.body,
            "Statut": STATUS_PREPARED,
        }
        for index, draft in enumerate(batch.drafts, start=1)
    ]
    snapshot_rows = [
        {
            "IDLot": batch_id,
            "SemaineDebut": datetime.combine(week_start, datetime.min.time()),
            "IDSegment": row.segment_id,
            "RessourceCle": row.resource_id,
            "NomRessource": row.resource_name,
            "ChargeProjetCle": row.project_manager_id,
            "NumeroProjet": row.project_number,
            "NomProjet": row.project_name,
            "Date": datetime.combine(row.day, datetime.min.time()),
            "Heures": round(float(row.hours), 2),
            "TypeAllocation": row.allocation_type,
            "HorsHoraire": "Oui" if row.outside_schedule else "Non",
            "Confirmation": row.confirmation,
        }
        for row in assignments
    ]

    with repo._lock:
        _append_rows(repo, BATCH_SHEET, BATCH_TABLE, BATCH_HEADERS, [batch_row])
        _append_rows(repo, MESSAGE_SHEET, MESSAGE_TABLE, MESSAGE_HEADERS, message_rows)
        _append_rows(repo, SNAPSHOT_SHEET, SNAPSHOT_TABLE, SNAPSHOT_HEADERS, snapshot_rows)
        repo.save()
    return batch_id


def _set_message_status(repo: ExcelRepository, batch_id: str, status: str) -> None:
    sheet = repo._book().sheets[MESSAGE_SHEET]
    matrix = _as_matrix(sheet.used_range.value)
    if not matrix:
        return
    headers = [str(value or "") for value in matrix[0]]
    try:
        lot_col = headers.index("IDLot") + 1
        status_col = headers.index("Statut") + 1
    except ValueError:
        return
    for row_number, row in enumerate(matrix[1:], start=2):
        value = row[lot_col - 1] if lot_col - 1 < len(row) else None
        if str(value or "") == str(batch_id):
            sheet.range((row_number, status_col)).value = status


def mark_stale_open_batches_obsolete(
    repo: ExcelRepository,
    week_start: date,
    current_fingerprint: str,
) -> int:
    """Persist stale prepared/approved lots as obsolete; communicated lots are immutable."""
    ensure_communication_sheets(repo)
    rows = [
        row
        for row in repo._sheet_as_records(BATCH_SHEET, "IDLot")
        if _date_from_any(row.get("SemaineDebut")) == week_start
        and is_stale_open_batch(
            str(row.get("Statut") or ""),
            str(row.get("EmpreintePlanning") or ""),
            current_fingerprint,
        )
    ]
    if not rows:
        return 0

    with repo._lock:
        sheet = repo._book().sheets[BATCH_SHEET]
        status_col = BATCH_HEADERS.index("Statut") + 1
        for record in rows:
            state = mark_obsolete(_batch_state_from_row(record))
            batch_id = state.batch_id
            row_number = _locate_batch_row(repo, batch_id)
            sheet.range((row_number, status_col)).value = STATUS_OBSOLETE
            _set_message_status(repo, batch_id, STATUS_OBSOLETE)
        repo.save()
    return len(rows)


def approve_persisted_batch(
    repo: ExcelRepository,
    batch_id: str,
    *,
    approved_by: str,
    approved_at: datetime | None = None,
) -> None:
    ensure_communication_sheets(repo)
    approved_at = approved_at or datetime.now()
    current = _batch_state_from_row(_batch_record(repo, batch_id))
    updated = approve_batch(current, approved_by=approved_by, approved_at=approved_at)
    with repo._lock:
        row = _locate_batch_row(repo, batch_id)
        sheet = repo._book().sheets[BATCH_SHEET]
        sheet.range((row, BATCH_HEADERS.index("Statut") + 1)).value = updated.status
        sheet.range((row, BATCH_HEADERS.index("ApprouvePar") + 1)).value = updated.approved_by
        sheet.range((row, BATCH_HEADERS.index("DateApprobation") + 1)).value = updated.approved_at
        _set_message_status(repo, batch_id, STATUS_APPROVED)
        repo.save()


def mark_persisted_batch_communicated(
    repo: ExcelRepository,
    batch_id: str,
    *,
    communicated_at: datetime | None = None,
) -> None:
    """Audit transition only. A future UI must expose this solely as an explicit manual action."""
    ensure_communication_sheets(repo)
    communicated_at = communicated_at or datetime.now()
    current = _batch_state_from_row(_batch_record(repo, batch_id))
    updated = mark_communicated(current, communicated_at=communicated_at)
    with repo._lock:
        row = _locate_batch_row(repo, batch_id)
        sheet = repo._book().sheets[BATCH_SHEET]
        sheet.range((row, BATCH_HEADERS.index("Statut") + 1)).value = updated.status
        sheet.range((row, BATCH_HEADERS.index("DateCommunication") + 1)).value = updated.communicated_at
        _set_message_status(repo, batch_id, STATUS_COMMUNICATED)
        repo.save()


def latest_communicated_snapshot(repo: ExcelRepository, week_start: date) -> tuple[str, list[WeeklyAssignment]]:
    ensure_communication_sheets(repo)
    batches = [
        row
        for row in repo._sheet_as_records(BATCH_SHEET, "IDLot")
        if _date_from_any(row.get("SemaineDebut")) == week_start
        and str(row.get("Statut") or "") == STATUS_COMMUNICATED
    ]
    if not batches:
        return "", []
    batches.sort(key=lambda row: str(row.get("DateCommunication") or ""), reverse=True)
    selected = batches[0]
    batch_id = str(selected.get("IDLot") or "")
    fingerprint = str(selected.get("EmpreintePlanning") or "")
    rows = [
        row
        for row in repo._sheet_as_records(SNAPSHOT_SHEET, "IDLot")
        if str(row.get("IDLot") or "") == batch_id
    ]
    assignments: list[WeeklyAssignment] = []
    for row in rows:
        day = _date_from_any(row.get("Date"))
        if not day:
            continue
        assignments.append(
            WeeklyAssignment(
                segment_id=str(row.get("IDSegment") or ""),
                resource_id=str(row.get("RessourceCle") or ""),
                resource_name=str(row.get("NomRessource") or ""),
                project_manager_id=str(row.get("ChargeProjetCle") or ""),
                project_number=str(row.get("NumeroProjet") or ""),
                project_name=str(row.get("NomProjet") or ""),
                day=day,
                hours=float(row.get("Heures") or 0.0),
                allocation_type=str(row.get("TypeAllocation") or "Flexible"),
                outside_schedule=_truthy(row.get("HorsHoraire")),
                confirmation=str(row.get("Confirmation") or "Confirmée"),
            )
        )
    return fingerprint, assignments
