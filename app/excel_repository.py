from __future__ import annotations

import getpass
import hashlib
import json
import math
import re
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

import xlwings as xw


DEMAND_HEADERS = [
    "NoDemande",
    "NumeroProjet",
    "NomProjet",
    "Client",
    "Demandeur",
    "ChargeProjet",
    "TypeDemande",
    "Priorite",
    "DateDebutSouhaitee",
    "DateFinSouhaitee",
    "Description",
    "Statut",
    "SiteClient",
    "Lieu",
    "NombreRessources",
    "CompetencesRequises",
    "TempsEstimeHeures",
    "TempsEstimeJours",
    "TechnicienPropose",
    "DateCreation",
    "DateModification",
    "ApprouvePar",
    "DateApprobation",
    "CommentaireApprobation",
]

HISTORY_HEADERS = [
    "Horodatage",
    "NoDemande",
    "Action",
    "AncienStatut",
    "NouveauStatut",
    "Utilisateur",
    "Commentaire",
    "Details",
]

REQUEST_STATUSES = [
    "Brouillon",
    "Soumise",
    "En planification",
    "À corriger",
    "Annulée",
    "Fermé",
]

EFFORT_STATUSES = [
    "EN ATTENTE",
    "À FAIRE",
    "EN COURS",
    "TERMINÉ",
    "ANNULÉ",
    "FERMÉ",
]

# Les feuilles maîtres sont éditables dans l'écran "Données Excel".
# Historique est volontairement en lecture seule pour préserver l'audit.
MASTER_SHEETS = {
    "Configuration des listes",
    "Liste des projets",
    "Liste des efforts",
    "Liste_Effort",
    "DemandesMO",
}


@dataclass(slots=True)
class SheetGrid:
    sheet_name: str
    header_row: int
    columns: list[dict[str, Any]]
    rows: list[dict[str, Any]]
    field_to_col: dict[str, int]
    signature: str


def _as_matrix(value: Any) -> list[list[Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        return [[value]]
    if not value:
        return []
    if isinstance(value[0], list):
        return value
    return [value]


def _serializable(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.time() == datetime.min.time():
            return value.date().isoformat()
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return round(value, 6)
    return value


def _date_from_any(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        return (datetime(1899, 12, 30) + timedelta(days=float(value))).date()

    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text[:19], fmt).date()
        except ValueError:
            continue
    return None


def _excel_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    # Certaines cellules "Efforts Prévus" du classeur sont formatées en date.
    # xlwings les retourne alors comme datetime; on récupère le nombre Excel.
    if isinstance(value, datetime):
        return float((value - datetime(1899, 12, 30)).days)
    if isinstance(value, date):
        return float(
            (datetime.combine(value, datetime.min.time()) - datetime(1899, 12, 30)).days
        )
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


def _excel_col_letter(col: int) -> str:
    result = ""
    n = col
    while n:
        n, remainder = divmod(n - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _best_header_row(matrix: list[list[Any]], max_scan: int = 15) -> int:
    """Détecte la ligne d'en-tête la plus probable dans les 15 premières lignes."""
    if not matrix:
        return 1
    best_idx = 0
    best_score = -1.0
    for idx, row in enumerate(matrix[:max_scan]):
        nonempty = [v for v in row if v not in (None, "")]
        if not nonempty:
            continue
        strings = sum(isinstance(v, str) for v in nonempty)
        unique_strings = len(
            {str(v).strip().lower() for v in nonempty if isinstance(v, str)}
        )
        score = len(nonempty) + strings * 1.5 + unique_strings * 0.25
        if strings < max(2, len(nonempty) // 2):
            score *= 0.6
        if score > best_score:
            best_idx = idx
            best_score = score
    return best_idx + 1


class ExcelRepository:
    """Pont live entre l'application et le classeur ouvert dans Microsoft Excel."""

    def __init__(self, workbook_path: str | Path | None, save_on_write: bool = True):
        self.path = Path(workbook_path).resolve() if workbook_path else None
        self.save_on_write = save_on_write
        self._lock = threading.RLock()
        self.book: xw.Book | None = None
        self.current_user = getpass.getuser()

    # ------------------------------------------------------------------
    # Connexion / cycle de vie
    # ------------------------------------------------------------------
    @property
    def is_configured(self) -> bool:
        return self.path is not None

    @property
    def is_connected(self) -> bool:
        if self.book is None:
            return False
        try:
            _ = self.book.name
            return True
        except Exception:
            return False

    def set_path(self, workbook_path: str | Path | None) -> None:
        with self._lock:
            self.path = Path(workbook_path).resolve() if workbook_path else None
            self.book = None

    def connect(self) -> None:
        with self._lock:
            if self.path is None:
                raise FileNotFoundError("Aucun fichier Excel n'est configuré.")
            if not self.path.exists():
                raise FileNotFoundError(f"Le classeur est introuvable : {self.path}")
            if self.path.suffix.lower() not in {".xlsx", ".xlsm"}:
                raise ValueError("Le fichier sélectionné doit être un classeur .xlsx ou .xlsm.")

            wanted = str(self.path).lower()
            try:
                apps = list(xw.apps)
            except Exception:
                apps = []

            for app in apps:
                for book in app.books:
                    try:
                        if str(Path(book.fullname).resolve()).lower() == wanted:
                            self.book = book
                            self.ensure_app_sheets()
                            return
                    except Exception:
                        continue

            self.book = xw.Book(str(self.path))
            self.ensure_app_sheets()

    def _book(self) -> xw.Book:
        if not self.is_connected:
            self.connect()
        assert self.book is not None
        return self.book

    def save(self) -> None:
        if self.save_on_write:
            self._book().save()

    def sheet_names(self) -> list[str]:
        with self._lock:
            return [s.name for s in self._book().sheets]

    def ensure_app_sheets(self) -> None:
        self._ensure_sheet_table("DemandesMO", DEMAND_HEADERS, "DemandesMOTable")
        self._ensure_sheet_table("Historique", HISTORY_HEADERS, "HistoriqueTable")
        self.save()

    def _ensure_sheet_table(
        self, sheet_name: str, headers: list[str], table_name: str
    ) -> None:
        book = self._book()
        try:
            sheet = book.sheets[sheet_name]
        except Exception:
            sheet = book.sheets.add(sheet_name, after=book.sheets[-1])

        existing = _as_matrix(
            sheet.range((1, 1), (1, len(headers))).value
        )
        existing_headers = existing[0] if existing else []
        if existing_headers != headers:
            sheet.range((1, 1), (1, len(headers))).value = headers

        try:
            table_names = {table.name for table in sheet.tables}
        except Exception:
            table_names = set()

        if table_name not in table_names:
            try:
                source = sheet.range((1, 1), (2, len(headers)))
                table = sheet.tables.add(source=source, name=table_name)
                table.show_autofilter = True
            except Exception:
                pass

        header = sheet.range((1, 1), (1, len(headers)))
        header.color = (31, 78, 121)
        header.font.bold = True
        header.font.color = (255, 255, 255)
        try:
            header.api.HorizontalAlignment = -4108  # xlCenter
        except Exception:
            pass

        try:
            sheet.autofit(axis="columns")
        except Exception:
            pass

        for i, title in enumerate(headers, start=1):
            try:
                if "Description" in title or "Commentaire" in title or title == "Details":
                    sheet.range((1, i), (1000, i)).column_width = 32
                elif "Date" in title or title == "Horodatage":
                    sheet.range((1, i), (1000, i)).column_width = 18
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Éditeur générique des feuilles
    # ------------------------------------------------------------------
    def read_sheet_grid(self, sheet_name: str, max_rows: int = 1500) -> SheetGrid:
        with self._lock:
            sheet = self._book().sheets[sheet_name]
            used = sheet.used_range
            start_row, start_col = used.row, used.column
            matrix = _as_matrix(used.value)
            formulas = _as_matrix(used.formula)
            if not matrix:
                return SheetGrid(sheet_name, 1, [], [], {}, "empty")

            relative_header = _best_header_row(matrix)
            header_idx = relative_header - 1
            header_row = start_row + header_idx
            headers = matrix[header_idx]

            keep_cols: list[int] = []
            for idx in range(len(headers)):
                header = headers[idx] if idx < len(headers) else None
                has_data = any(
                    idx < len(row) and row[idx] not in (None, "")
                    for row in matrix[
                        header_idx + 1 : min(len(matrix), header_idx + max_rows + 1)
                    ]
                )
                if header not in (None, "") or has_data:
                    keep_cols.append(idx)

            columns: list[dict[str, Any]] = []
            field_to_col: dict[str, int] = {}
            seen_headers: dict[str, int] = {}

            for idx in keep_cols:
                abs_col = start_col + idx
                letter = _excel_col_letter(abs_col)
                raw_header = headers[idx] if idx < len(headers) else None
                base = (
                    str(raw_header).strip()
                    if raw_header not in (None, "")
                    else f"Colonne {letter}"
                )
                seen_headers[base] = seen_headers.get(base, 0) + 1
                display = (
                    base
                    if seen_headers[base] == 1
                    else f"{base} [{letter}]"
                )
                field = f"c{abs_col}"
                field_to_col[field] = abs_col
                columns.append(
                    {
                        "headerName": display,
                        "field": field,
                        "minWidth": 120,
                        "filter": True,
                        "sortable": True,
                        "resizable": True,
                        "editable": sheet_name in MASTER_SHEETS,
                    }
                )

            rows: list[dict[str, Any]] = []
            end_idx = min(len(matrix), header_idx + max_rows + 1)
            for rel_idx in range(header_idx + 1, end_idx):
                row = matrix[rel_idx]
                if not any(
                    idx < len(row) and row[idx] not in (None, "")
                    for idx in keep_cols
                ):
                    continue
                item: dict[str, Any] = {"_excel_row": start_row + rel_idx}
                formula_cols: list[int] = []
                for idx in keep_cols:
                    abs_col = start_col + idx
                    item[f"c{abs_col}"] = _serializable(
                        row[idx] if idx < len(row) else None
                    )
                    formula = None
                    if rel_idx < len(formulas) and idx < len(formulas[rel_idx]):
                        formula = formulas[rel_idx][idx]
                    if isinstance(formula, str) and formula.startswith("="):
                        formula_cols.append(abs_col)
                if formula_cols:
                    item["_formula_cols"] = formula_cols
                rows.append(item)

            return SheetGrid(
                sheet_name,
                header_row,
                columns,
                rows,
                field_to_col,
                self._hash_matrix(matrix),
            )

    def update_sheet_cell(
        self, sheet_name: str, row: int, col: int, value: Any
    ) -> None:
        with self._lock:
            sheet = self._book().sheets[sheet_name]
            cell = sheet.range((row, col))
            formula = cell.formula
            if isinstance(formula, str) and formula.startswith("="):
                raise ValueError(
                    "Cette cellule contient une formule Excel et est protégée dans la V1."
                )

            parsed = self._parse_grid_value(sheet, col, value)
            cell.value = parsed
            self.save()

    def append_blank_row(self, sheet_name: str) -> int:
        if sheet_name not in MASTER_SHEETS:
            raise ValueError("Cette feuille est en lecture seule dans la V1.")

        with self._lock:
            sheet = self._book().sheets[sheet_name]
            grid = self.read_sheet_grid(sheet_name)
            if not grid.columns:
                raise ValueError("Aucune table détectée dans cette feuille.")

            target = max(sheet.used_range.last_cell.row + 1, grid.header_row + 1)
            first_col = min(grid.field_to_col.values())
            last_col = max(grid.field_to_col.values())
            sheet.range((target, first_col), (target, last_col)).value = [
                None
            ] * (last_col - first_col + 1)

            # Si une table Excel englobe la plage, on tente de l'agrandir.
            try:
                for table in sheet.tables:
                    if table.range.row <= grid.header_row <= table.range.last_cell.row:
                        table.resize(
                            sheet.range(
                                (table.range.row, table.range.column),
                                (target, table.range.last_cell.column),
                            )
                        )
            except Exception:
                pass

            self.save()
            return target

    def _parse_grid_value(self, sheet: xw.Sheet, col: int, value: Any) -> Any:
        if value in (None, ""):
            return None

        matrix = _as_matrix(sheet.used_range.value)
        header_rel = _best_header_row(matrix)
        header_row = sheet.used_range.row + header_rel - 1
        header = sheet.range((header_row, col)).value
        header_text = str(header or "").lower()

        if (
            "date" in header_text
            or "début" in header_text
            or "fin" in header_text
            or "mise à jour" in header_text
        ):
            parsed_date = _date_from_any(value)
            if parsed_date:
                return datetime.combine(parsed_date, datetime.min.time())

        return value

    def signature(self, sheet_names: Iterable[str]) -> str:
        with self._lock:
            h = hashlib.sha1()
            book = self._book()
            existing = {s.name for s in book.sheets}
            for name in sheet_names:
                if name not in existing:
                    continue
                matrix = _as_matrix(book.sheets[name].used_range.value)
                h.update(name.encode("utf-8"))
                h.update(self._hash_matrix(matrix).encode("ascii"))
            return h.hexdigest()

    @staticmethod
    def _hash_matrix(matrix: list[list[Any]]) -> str:
        serial = [[_serializable(v) for v in row] for row in matrix]
        payload = json.dumps(
            serial, ensure_ascii=False, default=str, separators=(",", ":")
        )
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # Lecture métier
    # ------------------------------------------------------------------
    def _sheet_as_records(
        self, sheet_name: str, expected_header: str | None = None
    ) -> list[dict[str, Any]]:
        sheet = self._book().sheets[sheet_name]
        used = sheet.used_range
        matrix = _as_matrix(used.value)
        if not matrix:
            return []

        header_rel = _best_header_row(matrix)
        if expected_header:
            for idx, row in enumerate(matrix[:20]):
                if expected_header in row:
                    header_rel = idx + 1
                    break

        headers = matrix[header_rel - 1]
        records: list[dict[str, Any]] = []
        first_data_excel_row = used.row + header_rel

        for offset, row in enumerate(matrix[header_rel:]):
            if not any(v not in (None, "") for v in row):
                continue
            item: dict[str, Any] = {
                "_row": first_data_excel_row + offset
            }
            for col_idx, header in enumerate(headers):
                if header in (None, ""):
                    continue
                key = str(header).strip()
                if key in item:
                    key = (
                        f"{key} "
                        f"[{_excel_col_letter(used.column + col_idx)}]"
                    )
                item[key] = (
                    row[col_idx] if col_idx < len(row) else None
                )
            records.append(item)

        return records

    def projects(self, active_only: bool = False) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._sheet_as_records(
                "Liste des projets", "Numéro de Projet"
            )
            if active_only:
                rows = [
                    r
                    for r in rows
                    if str(r.get("État", "")).strip().lower()
                    not in {"terminé", "annulé"}
                ]
            return rows

    def technicians(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._sheet_as_records(
                "Configuration des listes", "Équipe/Technicien"
            )
            result: list[dict[str, Any]] = []

            for row in rows:
                name = row.get("Équipe/Technicien")
                if not name:
                    continue
                name = str(name).strip()
                if name.lower().startswith("team "):
                    continue

                description = row.get("Description")
                capacity = _excel_number(row.get("Capacity")) or 0.0

                if description or capacity > 0:
                    result.append(
                        {
                            "name": name,
                            "description": str(description or ""),
                            "team": str(row.get("Team") or ""),
                            "capacity": capacity,
                        }
                    )
            return result

    def competencies(self) -> list[str]:
        with self._lock:
            rows = self._sheet_as_records(
                "Configuration des listes", "Compétence"
            )
            values: list[str] = []
            for row in rows:
                value = row.get("Compétence")
                text = str(value).strip() if value else ""
                if text and text not in values:
                    values.append(text)
            return values

    def expertise_for_competency(
        self, competency: str | None
    ) -> str | None:
        if not competency:
            return None
        with self._lock:
            rows = self._sheet_as_records(
                "Configuration des listes", "Compétence"
            )
            for row in rows:
                if (
                    str(row.get("Compétence") or "").strip()
                    == competency
                ):
                    return (
                        str(
                            row.get("Champs d'expertise") or ""
                        ).strip()
                        or None
                    )
        return None

    def efforts(self, include_closed: bool = True) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._sheet_as_records(
                "Liste_Effort", "N° projet"
            )
            result = []
            for row in rows:
                row["Date de début"] = _date_from_any(
                    row.get("Date de début")
                )
                row["Date de fin"] = _date_from_any(
                    row.get("Date de fin")
                )
                row["Efforts Prévus"] = _excel_number(
                    row.get("Efforts Prévus")
                )
                status = str(row.get("Status") or "").upper()
                if (
                    not include_closed
                    and status in {"FERMÉ", "TERMINÉ", "ANNULÉ"}
                ):
                    continue
                result.append(row)
            return result

    def update_effort(
        self, row_number: int, updates: dict[str, Any]
    ) -> None:
        with self._lock:
            sheet = self._book().sheets["Liste_Effort"]
            last_col = sheet.used_range.last_cell.column
            headers = _as_matrix(
                sheet.range((1, 1), (1, last_col)).value
            )[0]
            header_map = {
                str(v).strip(): idx + 1
                for idx, v in enumerate(headers)
                if v not in (None, "")
            }

            for key, value in updates.items():
                col = header_map.get(key)
                if not col:
                    continue
                if key in {"Date de début", "Date de fin"}:
                    d = _date_from_any(value)
                    value = (
                        datetime.combine(d, datetime.min.time())
                        if d
                        else None
                    )
                elif key == "Efforts Prévus":
                    value = _excel_number(value)
                sheet.range((row_number, col)).value = value

            self.save()

    def append_effort(self, values: dict[str, Any]) -> int:
        with self._lock:
            sheet = self._book().sheets["Liste_Effort"]
            last_col = sheet.used_range.last_cell.column
            headers = _as_matrix(
                sheet.range((1, 1), (1, last_col)).value
            )[0]
            target = sheet.used_range.last_cell.row + 1

            row_values: list[Any] = []
            for header in headers:
                if header in (None, ""):
                    row_values.append(None)
                    continue
                key = str(header).strip()
                value = values.get(key)
                if key in {"Date de début", "Date de fin"}:
                    d = _date_from_any(value)
                    value = (
                        datetime.combine(d, datetime.min.time())
                        if d
                        else None
                    )
                row_values.append(value)

            sheet.range(
                (target, 1), (target, len(headers))
            ).value = row_values

            try:
                for table in sheet.tables:
                    if table.range.last_cell.row < target:
                        table.resize(
                            sheet.range(
                                (table.range.row, table.range.column),
                                (
                                    target,
                                    table.range.last_cell.column,
                                ),
                            )
                        )
            except Exception:
                pass

            self.save()
            return target

    # ------------------------------------------------------------------
    # Demandes / approbations / historique
    # ------------------------------------------------------------------
    def demands(self) -> list[dict[str, Any]]:
        with self._lock:
            sheet = self._book().sheets["DemandesMO"]
            matrix = _as_matrix(sheet.used_range.value)
            if not matrix:
                return []

            headers = matrix[0]
            rows: list[dict[str, Any]] = []

            for excel_row, row in enumerate(matrix[1:], start=2):
                if not row or row[0] in (None, ""):
                    continue
                item: dict[str, Any] = {"_row": excel_row}
                for idx, header in enumerate(headers):
                    if header in (None, ""):
                        continue
                    item[str(header)] = (
                        row[idx] if idx < len(row) else None
                    )

                item["DateDebutSouhaitee"] = _date_from_any(
                    item.get("DateDebutSouhaitee")
                )
                item["DateFinSouhaitee"] = _date_from_any(
                    item.get("DateFinSouhaitee")
                )
                rows.append(item)

            return rows

    def next_request_number(self) -> str:
        year = date.today().year
        max_seq = 0
        pattern = re.compile(
            rf"^DMO-{year}-(\d+)$", re.IGNORECASE
        )

        for demand in self.demands():
            number = str(demand.get("NoDemande") or "")
            match = pattern.match(number)
            if match:
                max_seq = max(max_seq, int(match.group(1)))

        return f"DMO-{year}-{max_seq + 1:04d}"

    def create_demand(
        self, data: dict[str, Any], submit: bool = False
    ) -> str:
        with self._lock:
            number = self.next_request_number()
            now = datetime.now()
            values = {key: None for key in DEMAND_HEADERS}
            values.update(data)
            values["NoDemande"] = number
            values["Statut"] = (
                "Soumise" if submit else "Brouillon"
            )
            values["Demandeur"] = (
                values.get("Demandeur") or self.current_user
            )
            values["DateCreation"] = now
            values["DateModification"] = now

            self._append_dict_row(
                "DemandesMO",
                DEMAND_HEADERS,
                values,
                "DemandesMOTable",
            )
            self.log_history(
                number,
                "Création",
                "",
                values["Statut"],
                "Demande créée",
            )
            return number

    def update_demand(
        self,
        number: str,
        updates: dict[str, Any],
        action: str = "Modification",
        comment: str = "",
    ) -> None:
        with self._lock:
            sheet = self._book().sheets["DemandesMO"]
            row = next(
                (
                    r
                    for r in self.demands()
                    if str(r.get("NoDemande")) == number
                ),
                None,
            )
            if not row:
                raise KeyError(f"Demande {number} introuvable")

            old_status = str(row.get("Statut") or "")
            headers = _as_matrix(
                sheet.range(
                    (1, 1), (1, len(DEMAND_HEADERS))
                ).value
            )[0]
            header_map = {
                str(v): idx + 1
                for idx, v in enumerate(headers)
                if v not in (None, "")
            }

            updates = dict(updates)
            updates["DateModification"] = datetime.now()

            for key, value in updates.items():
                col = header_map.get(key)
                if not col:
                    continue
                if key in {
                    "DateDebutSouhaitee",
                    "DateFinSouhaitee",
                }:
                    d = _date_from_any(value)
                    value = (
                        datetime.combine(d, datetime.min.time())
                        if d
                        else None
                    )
                sheet.range((row["_row"], col)).value = value

            self.save()
            new_status = str(
                updates.get("Statut", old_status) or ""
            )
            self.log_history(
                number,
                action,
                old_status,
                new_status,
                comment,
            )

    def submit_demand(self, number: str) -> None:
        self.update_demand(
            number,
            {"Statut": "Soumise"},
            action="Soumission",
            comment="Demande soumise pour approbation",
        )

    def approve_demand(
        self, number: str, comment: str = ""
    ) -> None:
        self.update_demand(
            number,
            {
                "Statut": "En planification",
                "ApprouvePar": self.current_user,
                "DateApprobation": datetime.now(),
                "CommentaireApprobation": comment,
            },
            action="Approbation",
            comment=comment or "Demande approuvée",
        )

    def request_correction(
        self, number: str, comment: str
    ) -> None:
        self.update_demand(
            number,
            {
                "Statut": "À corriger",
                "CommentaireApprobation": comment,
            },
            action="Retour pour correction",
            comment=comment,
        )

    def close_demand_as_planned(
        self, number: str, effort_row: int
    ) -> None:
        self.update_demand(
            number,
            {"Statut": "Fermé"},
            action="Planification",
            comment=(
                "Affectation créée dans Liste_Effort, "
                f"ligne Excel {effort_row}"
            ),
        )

    def log_history(
        self,
        number: str,
        action: str,
        old_status: str,
        new_status: str,
        comment: str = "",
        details: str = "",
    ) -> None:
        values = {
            "Horodatage": datetime.now(),
            "NoDemande": number,
            "Action": action,
            "AncienStatut": old_status,
            "NouveauStatut": new_status,
            "Utilisateur": self.current_user,
            "Commentaire": comment,
            "Details": details,
        }
        self._append_dict_row(
            "Historique",
            HISTORY_HEADERS,
            values,
            "HistoriqueTable",
        )

    def _append_dict_row(
        self,
        sheet_name: str,
        headers: list[str],
        values: dict[str, Any],
        table_name: str | None = None,
    ) -> int:
        sheet = self._book().sheets[sheet_name]
        last = sheet.cells.last_cell.row
        last_used = sheet.range(f"A{last}").end("up").row
        target = max(2, last_used + 1)

        row_values = [values.get(header) for header in headers]
        for idx, header in enumerate(headers):
            if header in {
                "DateDebutSouhaitee",
                "DateFinSouhaitee",
            }:
                d = _date_from_any(row_values[idx])
                row_values[idx] = (
                    datetime.combine(d, datetime.min.time())
                    if d
                    else None
                )

        sheet.range(
            (target, 1), (target, len(headers))
        ).value = row_values

        if table_name:
            try:
                table = sheet.tables[table_name]
                table.resize(
                    sheet.range(
                        (1, 1), (target, len(headers))
                    )
                )
            except Exception:
                pass

        self.save()
        return target
