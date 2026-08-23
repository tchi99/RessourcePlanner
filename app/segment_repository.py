from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .excel_repository import ExcelRepository, MASTER_SHEETS, _as_matrix, _date_from_any


SEGMENT_SHEET = "SegmentsMO"
SEGMENT_TABLE = "SegmentsMOTable"
SEGMENT_HEADERS = [
    "IDSegment",
    "NoDemande",
    "NumeroProjet",
    "NomProjet",
    "Technicien",
    "DateDebut",
    "DateFin",
    "HeuresPrevues",
    "Statut",
    "Description",
    "SourceEffortRow",
    "DateCreation",
    "DateModification",
    "CreePar",
]
SEGMENT_STATUSES = ["Planifié", "En cours", "Terminé", "Annulé"]


def ensure_segment_sheet(repo: ExcelRepository) -> None:
    """Ensure the legacy Excel-backed SegmentsMO table exists.

    This is the stable repository boundary for SegmentsMO during the V1.x to
    PostgreSQL migration. Schema migrations remain transitional for now, but page and
    application code no longer need to know that the data lives in v13.py.
    """
    MASTER_SHEETS.add(SEGMENT_SHEET)
    try:
        repo._book().sheets[SEGMENT_SHEET]
        return
    except Exception:
        repo._ensure_sheet_table(SEGMENT_SHEET, SEGMENT_HEADERS, SEGMENT_TABLE)
        repo.save()


def number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def _excel_datetime(value: Any) -> datetime | None:
    parsed = _date_from_any(value)
    return datetime.combine(parsed, datetime.min.time()) if parsed else None


def segment_records(
    repo: ExcelRepository,
    include_cancelled: bool = True,
) -> list[dict[str, Any]]:
    with repo._lock:
        ensure_segment_sheet(repo)
        rows = repo._sheet_as_records(SEGMENT_SHEET, "IDSegment")
        result: list[dict[str, Any]] = []
        for row in rows:
            if not row.get("IDSegment"):
                continue
            row["DateDebut"] = _date_from_any(row.get("DateDebut"))
            row["DateFin"] = _date_from_any(row.get("DateFin"))
            row["HeuresPrevues"] = number(row.get("HeuresPrevues"))
            if not include_cancelled and str(row.get("Statut") or "") == "Annulé":
                continue
            result.append(row)
        return result


def _next_segment_id(repo: ExcelRepository) -> str:
    year = date.today().year
    max_seq = 0
    prefix = f"SEG-{year}-"
    for row in segment_records(repo):
        ident = str(row.get("IDSegment") or "")
        if ident.startswith(prefix):
            try:
                max_seq = max(max_seq, int(ident[len(prefix) :]))
            except ValueError:
                continue
    return f"{prefix}{max_seq + 1:04d}"


def add_segment(repo: ExcelRepository, values: dict[str, Any]) -> str:
    with repo._lock:
        ensure_segment_sheet(repo)
        ident = _next_segment_id(repo)
        now = datetime.now()
        payload = {header: None for header in SEGMENT_HEADERS}
        payload.update(values)
        payload["IDSegment"] = ident
        payload["Statut"] = payload.get("Statut") or "Planifié"
        payload["DateDebut"] = _excel_datetime(payload.get("DateDebut"))
        payload["DateFin"] = _excel_datetime(
            payload.get("DateFin") or payload.get("DateDebut")
        )
        payload["HeuresPrevues"] = number(payload.get("HeuresPrevues"))
        payload["DateCreation"] = now
        payload["DateModification"] = now
        payload["CreePar"] = repo.current_user
        repo._append_dict_row(
            SEGMENT_SHEET,
            SEGMENT_HEADERS,
            payload,
            SEGMENT_TABLE,
        )

        no_demande = str(payload.get("NoDemande") or "")
        if no_demande:
            demand = next(
                (
                    demand
                    for demand in repo.demands()
                    if str(demand.get("NoDemande") or "") == no_demande
                ),
                None,
            )
            status = str(demand.get("Statut") or "") if demand else ""
            repo.log_history(
                no_demande,
                "Création segment",
                status,
                status,
                f"{ident} créé pour {payload.get('Technicien') or ''}",
                details=(
                    f"{payload.get('DateDebut')} → {payload.get('DateFin')} · "
                    f"{payload.get('HeuresPrevues')} h"
                ),
            )
        return ident


def update_segment(
    repo: ExcelRepository,
    ident: str,
    updates: dict[str, Any],
) -> None:
    with repo._lock:
        row = next(
            (
                record
                for record in segment_records(repo)
                if str(record.get("IDSegment") or "") == ident
            ),
            None,
        )
        if not row:
            raise KeyError(f"Segment {ident} introuvable")

        sheet = repo._book().sheets[SEGMENT_SHEET]
        headers = _as_matrix(
            sheet.range((1, 1), (1, len(SEGMENT_HEADERS))).value
        )[0]
        header_map = {
            str(value).strip(): index + 1
            for index, value in enumerate(headers)
            if value not in (None, "")
        }
        updates = dict(updates)
        updates["DateModification"] = datetime.now()
        for key, value in updates.items():
            column = header_map.get(key)
            if not column:
                continue
            if key in {"DateDebut", "DateFin"}:
                value = _excel_datetime(value)
            elif key == "HeuresPrevues":
                value = number(value)
            sheet.range((int(row["_row"]), column)).value = value
        repo.save()

        no_demande = str(row.get("NoDemande") or "")
        if no_demande:
            demand = next(
                (
                    demand
                    for demand in repo.demands()
                    if str(demand.get("NoDemande") or "") == no_demande
                ),
                None,
            )
            status = str(demand.get("Statut") or "") if demand else ""
            repo.log_history(
                no_demande,
                "Modification segment",
                status,
                status,
                f"{ident} modifié",
            )
