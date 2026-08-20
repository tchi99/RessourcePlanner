from __future__ import annotations

from datetime import datetime
from typing import Any

from .communication_excel import CONTACT_HEADERS, CONTACT_SHEET, CONTACT_TABLE
from .communication_queries import ensure_communication_registry_once
from .domain.contact_directory import build_contact_candidates, missing_contact_candidates
from .excel_repository import ExcelRepository, _as_matrix


def contact_directory_records(repo: ExcelRepository) -> list[dict[str, Any]]:
    ensure_communication_registry_once(repo)
    rows = repo._sheet_as_records(CONTACT_SHEET, "PersonneCle")
    rows = [row for row in rows if str(row.get("PersonneCle") or "").strip()]
    rows.sort(
        key=lambda row: (
            str(row.get("TypePersonne") or "").casefold(),
            str(row.get("PersonneCle") or "").casefold(),
        )
    )
    return rows


def synchronize_known_contacts(repo: ExcelRepository) -> int:
    """Add missing technicians/project managers without overwriting user-entered data."""
    ensure_communication_registry_once(repo)
    with repo._lock:
        technician_rows = repo.technicians()
        demand_rows = repo._sheet_as_records("DemandesMO", "NoDemande")
        existing_rows = repo._sheet_as_records(CONTACT_SHEET, "PersonneCle")
        candidates = build_contact_candidates(technician_rows, demand_rows)
        missing = missing_contact_candidates(candidates, existing_rows)
        if not missing:
            return 0

        now = datetime.now()
        rows = [
            {
                "PersonneCle": candidate.person_id,
                "TypePersonne": candidate.person_type,
                "NomAffiche": candidate.display_name,
                "Courriel": "",
                "Actif": "Oui",
                "DateModification": now,
            }
            for candidate in missing
        ]

        sheet = repo._book().sheets[CONTACT_SHEET]
        last = max(int(sheet.used_range.last_cell.row), 1)
        start = last + 1
        matrix = [[row.get(header) for header in CONTACT_HEADERS] for row in rows]
        sheet.range(
            (start, 1),
            (start + len(matrix) - 1, len(CONTACT_HEADERS)),
        ).value = matrix
        try:
            table = sheet.tables[CONTACT_TABLE]
            table.resize(
                sheet.range(
                    (1, 1),
                    (start + len(matrix) - 1, len(CONTACT_HEADERS)),
                )
            )
        except Exception:
            pass
        repo.save()
        return len(rows)


def _header_map(repo: ExcelRepository) -> dict[str, int]:
    sheet = repo._book().sheets[CONTACT_SHEET]
    headers = _as_matrix(
        sheet.range((1, 1), (1, len(CONTACT_HEADERS))).value
    )[0]
    return {
        str(value or "").strip(): index + 1
        for index, value in enumerate(headers)
        if value not in (None, "")
    }


def update_contact(
    repo: ExcelRepository,
    person_id: str,
    *,
    display_name: str,
    email: str,
    active: bool,
) -> None:
    ensure_communication_registry_once(repo)
    key = str(person_id or "").strip()
    if not key:
        raise ValueError("La clé de la personne est requise.")

    display = str(display_name or "").strip() or key
    address = str(email or "").strip()

    with repo._lock:
        target = next(
            (
                row
                for row in repo._sheet_as_records(CONTACT_SHEET, "PersonneCle")
                if str(row.get("PersonneCle") or "").strip() == key
            ),
            None,
        )
        if not target:
            raise KeyError(f"Contact introuvable: {key}")

        columns = _header_map(repo)
        sheet = repo._book().sheets[CONTACT_SHEET]
        row_number = int(target["_row"])
        values = {
            "NomAffiche": display,
            "Courriel": address,
            "Actif": "Oui" if active else "Non",
            "DateModification": datetime.now(),
        }
        for field, value in values.items():
            col = columns.get(field)
            if col:
                sheet.range((row_number, col)).value = value
        repo.save()
