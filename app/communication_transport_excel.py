from __future__ import annotations

from typing import Iterable

from .communication_excel import (
    BATCH_HEADERS,
    BATCH_SHEET,
    MESSAGE_SHEET,
    _batch_record,
    _batch_state_from_row,
    _locate_batch_row,
    _set_message_status,
    ensure_communication_sheets,
)
from .domain.communication_audit import (
    STATUS_DRAFTS_CREATED,
    STATUS_OBSOLETE,
    mark_drafts_created,
    mark_obsolete,
)
from .domain.communication_transport import MESSAGE_STATUS_DRAFT_CREATED
from .excel_repository import ExcelRepository, _as_matrix


def mark_persisted_message_drafts_created(
    repo: ExcelRepository,
    batch_id: str,
    message_ids: Iterable[str],
) -> tuple[int, int, bool]:
    """Mark successfully created/reused Outlook drafts and advance the batch if complete."""
    ensure_communication_sheets(repo)
    requested = {str(value or "").strip() for value in message_ids if str(value or "").strip()}
    current = _batch_state_from_row(_batch_record(repo, batch_id))
    # Validate the transition before mutating individual rows.
    candidate = mark_drafts_created(current)

    with repo._lock:
        sheet = repo._book().sheets[MESSAGE_SHEET]
        matrix = _as_matrix(sheet.used_range.value)
        if not matrix:
            return 0, 0, False
        headers = [str(value or "") for value in matrix[0]]
        try:
            id_col = headers.index("IDMessage") + 1
            lot_col = headers.index("IDLot") + 1
            status_col = headers.index("Statut") + 1
        except ValueError as exc:
            raise ValueError("Le registre des messages de communication est incomplet.") from exc

        updated = 0
        batch_rows: list[int] = []
        for row_number, row in enumerate(matrix[1:], start=2):
            lot_value = row[lot_col - 1] if lot_col - 1 < len(row) else None
            if str(lot_value or "") != str(batch_id):
                continue
            batch_rows.append(row_number)
            message_id = str(row[id_col - 1] if id_col - 1 < len(row) else "").strip()
            if message_id in requested:
                sheet.range((row_number, status_col)).value = MESSAGE_STATUS_DRAFT_CREATED
                updated += 1

        if not batch_rows:
            raise KeyError(f"Aucun message trouvé pour le lot {batch_id}.")

        statuses = [
            str(sheet.range((row_number, status_col)).value or "")
            for row_number in batch_rows
        ]
        complete = bool(statuses) and all(
            status == MESSAGE_STATUS_DRAFT_CREATED for status in statuses
        )
        if complete:
            batch_row = _locate_batch_row(repo, batch_id)
            batch_sheet = repo._book().sheets[BATCH_SHEET]
            batch_sheet.range(
                (batch_row, BATCH_HEADERS.index("Statut") + 1)
            ).value = candidate.status
        repo.save()
        return updated, len(batch_rows), complete


def mark_persisted_draft_batch_obsolete(repo: ExcelRepository, batch_id: str) -> None:
    """Explicitly abandon an unsent batch whose Outlook drafts must no longer be used."""
    ensure_communication_sheets(repo)
    current = _batch_state_from_row(_batch_record(repo, batch_id))
    updated = mark_obsolete(current)
    with repo._lock:
        row = _locate_batch_row(repo, batch_id)
        sheet = repo._book().sheets[BATCH_SHEET]
        sheet.range((row, BATCH_HEADERS.index("Statut") + 1)).value = STATUS_OBSOLETE
        _set_message_status(repo, batch_id, STATUS_OBSOLETE)
        repo.save()


def batch_has_outlook_drafts(repo: ExcelRepository, batch_id: str) -> bool:
    current = _batch_state_from_row(_batch_record(repo, batch_id))
    return current.status == STATUS_DRAFTS_CREATED
