from __future__ import annotations

from datetime import date
from typing import Any

from .communication_excel import (
    BATCH_SHEET,
    CONTACT_SHEET,
    MESSAGE_SHEET,
    SNAPSHOT_SHEET,
    ensure_communication_sheets,
)
from .domain.communication_planning import Contact, WeeklyAssignment
from .domain.communication_source import weekly_assignments_from_records
from .excel_repository import ExcelRepository, _date_from_any


def ensure_communication_registry_once(repo: ExcelRepository) -> None:
    marker = str(repo.path or "")
    if getattr(repo, "_communication_registry_ready_path", None) == marker:
        return
    ensure_communication_sheets(repo)
    repo._communication_registry_ready_path = marker


def current_weekly_assignments(repo: ExcelRepository, week_start: date) -> list[WeeklyAssignment]:
    ensure_communication_registry_once(repo)
    with repo._lock:
        allocations = repo._sheet_as_records("AllocationsMO", "IDAllocation")
        segments = repo._sheet_as_records("SegmentsMO", "IDSegment")
        demands = repo._sheet_as_records("DemandesMO", "NoDemande")
    return weekly_assignments_from_records(allocations, segments, demands, week_start)


def contacts_by_id_without_reensure(repo: ExcelRepository) -> dict[str, Contact]:
    ensure_communication_registry_once(repo)
    rows = repo._sheet_as_records(CONTACT_SHEET, "PersonneCle")
    result: dict[str, Contact] = {}
    truthy = {"oui", "true", "1", "x", "yes", "actif", "active"}
    for row in rows:
        person_id = str(row.get("PersonneCle") or "").strip()
        email = str(row.get("Courriel") or "").strip()
        active_raw = row.get("Actif")
        active = True if active_raw in (None, "") else str(active_raw).strip().lower() in truthy
        if not person_id or not email or not active:
            continue
        result[person_id] = Contact(
            person_id=person_id,
            display_name=str(row.get("NomAffiche") or person_id).strip(),
            email=email,
        )
    return result


def latest_communicated_snapshot_without_reensure(
    repo: ExcelRepository, week_start: date
) -> tuple[str, list[WeeklyAssignment]]:
    ensure_communication_registry_once(repo)
    batches = [
        row
        for row in repo._sheet_as_records(BATCH_SHEET, "IDLot")
        if _date_from_any(row.get("SemaineDebut")) == week_start
        and str(row.get("Statut") or "") == "Communiqué"
    ]
    if not batches:
        return "", []
    batches.sort(key=lambda row: str(row.get("DateCommunication") or ""), reverse=True)
    selected = batches[0]
    batch_id = str(selected.get("IDLot") or "")
    fingerprint = str(selected.get("EmpreintePlanning") or "")
    snapshot_rows = [
        row
        for row in repo._sheet_as_records(SNAPSHOT_SHEET, "IDLot")
        if str(row.get("IDLot") or "") == batch_id
    ]
    assignments: list[WeeklyAssignment] = []
    truthy = {"oui", "true", "1", "x", "yes"}
    for row in snapshot_rows:
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
                allocation_type=str(row.get("TypeAllocation") or "Planifié"),
                outside_schedule=str(row.get("HorsHoraire") or "").strip().lower() in truthy,
                confirmation=str(row.get("Confirmation") or "Confirmée"),
            )
        )
    return fingerprint, assignments


def communication_batches_for_week(repo: ExcelRepository, week_start: date) -> list[dict[str, Any]]:
    ensure_communication_registry_once(repo)
    rows = [
        row
        for row in repo._sheet_as_records(BATCH_SHEET, "IDLot")
        if _date_from_any(row.get("SemaineDebut")) == week_start
    ]
    rows.sort(key=lambda row: str(row.get("DatePreparation") or ""), reverse=True)
    return rows


def communication_messages_for_batch(repo: ExcelRepository, batch_id: str) -> list[dict[str, Any]]:
    ensure_communication_registry_once(repo)
    return [
        row
        for row in repo._sheet_as_records(MESSAGE_SHEET, "IDMessage")
        if str(row.get("IDLot") or "") == str(batch_id)
    ]


def has_open_identical_batch(
    repo: ExcelRepository,
    *,
    week_start: date,
    message_kind: str,
    fingerprint: str,
) -> bool:
    return any(
        str(row.get("TypeCommunication") or "") == message_kind
        and str(row.get("EmpreintePlanning") or "") == fingerprint
        and str(row.get("Statut") or "") in {"Préparé", "Approuvé"}
        for row in communication_batches_for_week(repo, week_start)
    )
