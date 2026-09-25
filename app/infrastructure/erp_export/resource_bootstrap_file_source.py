from __future__ import annotations

import csv
from datetime import datetime, time
from pathlib import Path
from typing import Iterable, Mapping

from ...application.errors import ApplicationOperationError
from ...application.resource_admin import AVAILABILITY_WEEKDAYS
from ...application.resource_bootstrap import (
    BootstrapResourceRecord,
    BootstrapStandardSchedule,
    ResourceBootstrapSourcePort,
)
from .excel_project_source import _load_erp_workbook


_REQUIRED_COLUMNS = ("external_id", "name", "active", "resource_class")
_OPTIONAL_COLUMNS = ("email", "sort_order", "working_days", "start_time", "end_time")
_DAY_ALIASES = {
    "lun": "Lun", "lundi": "Lun", "mon": "Lun", "monday": "Lun",
    "mar": "Mar", "mardi": "Mar", "tue": "Mar", "tuesday": "Mar",
    "mer": "Mer", "mercredi": "Mer", "wed": "Mer", "wednesday": "Mer",
    "jeu": "Jeu", "jeudi": "Jeu", "thu": "Jeu", "thursday": "Jeu",
    "ven": "Ven", "vendredi": "Ven", "fri": "Ven", "friday": "Ven",
    "sam": "Sam", "samedi": "Sam", "sat": "Sam", "saturday": "Sam",
    "dim": "Dim", "dimanche": "Dim", "sun": "Dim", "sunday": "Dim",
}


def _text(value: object) -> str:
    return str(value or "").strip()


def _identifier(value: object) -> str:
    if isinstance(value, bool):
        return _text(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return _text(value)


def _header_key(value: object) -> str:
    return _text(value).casefold()


def _header_indexes(header: Iterable[object]) -> dict[str, int]:
    indexes = {
        _header_key(value): index
        for index, value in enumerate(header)
        if _header_key(value)
    }
    missing = [column for column in _REQUIRED_COLUMNS if column not in indexes]
    if missing:
        raise ApplicationOperationError(
            "Le fichier de bootstrap des ressources ne contient pas toutes les colonnes requises.",
            code="resource_bootstrap_headers_invalid",
            context={"missing_columns": missing},
        )
    return indexes


def _parse_bool(value: object, *, row_number: int) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    normalized = _text(value).casefold()
    if normalized in {"1", "true", "vrai", "oui", "yes", "y", "actif", "active"}:
        return True
    if normalized in {"0", "false", "faux", "non", "no", "n", "inactif", "inactive"}:
        return False
    raise ApplicationOperationError(
        "La colonne active doit contenir une valeur booléenne reconnue.",
        code="resource_bootstrap_active_invalid",
        context={"row": row_number},
    )


def _parse_sort_order(value: object, *, row_number: int) -> int | None:
    if value in (None, ""):
        return None
    try:
        number = float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError) as exc:
        raise ApplicationOperationError(
            "L'ordre d'affichage doit être un entier positif ou nul.",
            code="resource_bootstrap_sort_order_invalid",
            context={"row": row_number},
        ) from exc
    if not number.is_integer() or number < 0:
        raise ApplicationOperationError(
            "L'ordre d'affichage doit être un entier positif ou nul.",
            code="resource_bootstrap_sort_order_invalid",
            context={"row": row_number},
        )
    return int(number)


def _parse_time(value: object, *, row_number: int, field: str) -> time | None:
    if value in (None, ""):
        return None
    if isinstance(value, time):
        return value.replace(microsecond=0)
    if isinstance(value, datetime):
        return value.time().replace(microsecond=0)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        fraction = float(value)
        if 0 <= fraction < 1:
            minutes = int(round(fraction * 24 * 60))
            if minutes < 24 * 60:
                return time(hour=minutes // 60, minute=minutes % 60)
    raw = _text(value)
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).time()
        except ValueError:
            pass
    raise ApplicationOperationError(
        "Une heure de l'horaire standard est invalide.",
        code="resource_bootstrap_time_invalid",
        context={"row": row_number, "field": field},
    )


def _parse_weekdays(value: object, *, row_number: int) -> str | None:
    raw = _text(value)
    if not raw:
        return None
    tokens = [token.strip() for token in raw.replace(";", ",").split(",") if token.strip()]
    normalized: list[str] = []
    invalid: list[str] = []
    for token in tokens:
        day = _DAY_ALIASES.get(token.casefold())
        if day is None:
            invalid.append(token)
        elif day not in normalized:
            normalized.append(day)
    if invalid:
        raise ApplicationOperationError(
            "Un ou plusieurs jours ouvrés ne sont pas reconnus.",
            code="resource_bootstrap_weekdays_invalid",
            context={"row": row_number, "invalid": invalid},
        )
    return ",".join(day for day in AVAILABILITY_WEEKDAYS if day in normalized) or None


def _record(row: Mapping[str, object], *, row_number: int) -> BootstrapResourceRecord:
    external_id = _identifier(row.get("external_id"))
    name = _text(row.get("name"))
    resource_class = _text(row.get("resource_class"))
    if not external_id or not name or not resource_class:
        raise ApplicationOperationError(
            "Une ligne de bootstrap ressource est incomplète.",
            code="resource_bootstrap_row_invalid",
            context={"row": row_number},
        )

    weekdays = _parse_weekdays(row.get("working_days"), row_number=row_number)
    start = _parse_time(row.get("start_time"), row_number=row_number, field="start_time")
    end = _parse_time(row.get("end_time"), row_number=row_number, field="end_time")
    schedule_values = (weekdays, start, end)
    if any(value is not None for value in schedule_values) and not all(
        value is not None for value in schedule_values
    ):
        raise ApplicationOperationError(
            "working_days, start_time et end_time doivent être fournis ensemble.",
            code="resource_bootstrap_schedule_incomplete",
            context={"row": row_number},
        )
    schedule = (
        BootstrapStandardSchedule(weekdays=weekdays, start_time=start, end_time=end)
        if weekdays is not None and start is not None and end is not None
        else None
    )

    return BootstrapResourceRecord(
        external_id=external_id,
        name=name,
        email=_text(row.get("email")) or None,
        active=_parse_bool(row.get("active"), row_number=row_number),
        resource_class=resource_class,
        sort_order=_parse_sort_order(row.get("sort_order"), row_number=row_number),
        standard_schedule=schedule,
    )


def _validate_duplicates(
    rows: Iterable[BootstrapResourceRecord],
) -> tuple[BootstrapResourceRecord, ...]:
    result: list[BootstrapResourceRecord] = []
    seen: set[str] = set()
    for row in rows:
        if row.external_id in seen:
            raise ApplicationOperationError(
                "Le même external_id apparaît plus d'une fois dans le fichier.",
                code="resource_bootstrap_duplicate_external_id",
                context={"external_id": row.external_id},
            )
        seen.add(row.external_id)
        result.append(row)
    return tuple(result)


class ResourceBootstrapFileSource(ResourceBootstrapSourcePort):
    def __init__(self, path: str | Path, *, sheet_name: str = "Ressources") -> None:
        self._path = Path(path)
        self._sheet_name = sheet_name

    def _list_xlsx(self) -> tuple[BootstrapResourceRecord, ...]:
        try:
            workbook = _load_erp_workbook(self._path)
        except (OSError, TypeError, ValueError) as exc:
            raise ApplicationOperationError(
                "Impossible d'ouvrir le fichier de bootstrap des ressources.",
                code="resource_bootstrap_file_invalid",
                context={"path": str(self._path)},
            ) from exc
        try:
            if self._sheet_name not in workbook.sheetnames:
                raise ApplicationOperationError(
                    f"La feuille '{self._sheet_name}' est absente du fichier.",
                    code="resource_bootstrap_sheet_missing",
                    context={"sheet": self._sheet_name},
                )
            rows = workbook[self._sheet_name].iter_rows(values_only=True)
            header = next(rows, None)
            if header is None:
                raise ApplicationOperationError(
                    "La feuille de bootstrap des ressources est vide.",
                    code="resource_bootstrap_sheet_empty",
                    context={"sheet": self._sheet_name},
                )
            indexes = _header_indexes(header)
            result: list[BootstrapResourceRecord] = []
            for row_number, values in enumerate(rows, start=2):
                if not any(value not in (None, "") for value in values):
                    continue
                mapped = {
                    key: values[index] if index < len(values) else None
                    for key, index in indexes.items()
                    if key in _REQUIRED_COLUMNS or key in _OPTIONAL_COLUMNS
                }
                result.append(_record(mapped, row_number=row_number))
            return _validate_duplicates(result)
        finally:
            workbook.close()

    def _list_csv(self) -> tuple[BootstrapResourceRecord, ...]:
        raw: str | None = None
        for encoding in ("utf-8-sig", "cp1252"):
            try:
                raw = self._path.read_text(encoding=encoding)
                break
            except UnicodeDecodeError:
                continue
        if raw is None:
            raise ApplicationOperationError(
                "Impossible de décoder le fichier CSV des ressources.",
                code="resource_bootstrap_file_invalid",
                context={"path": str(self._path)},
            )
        try:
            dialect = csv.Sniffer().sniff(raw[:8192], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(raw.splitlines(), dialect=dialect)
        if reader.fieldnames is None:
            raise ApplicationOperationError(
                "Le fichier CSV des ressources est vide.",
                code="resource_bootstrap_sheet_empty",
                context={"path": str(self._path)},
            )
        _header_indexes(reader.fieldnames)
        result: list[BootstrapResourceRecord] = []
        for row_number, row in enumerate(reader, start=2):
            if not any(_text(value) for value in row.values()):
                continue
            normalized = {_header_key(key): value for key, value in row.items() if key is not None}
            result.append(_record(normalized, row_number=row_number))
        return _validate_duplicates(result)

    def list_resources(self) -> tuple[BootstrapResourceRecord, ...]:
        if not self._path.is_file():
            raise ApplicationOperationError(
                "Le fichier de bootstrap des ressources est introuvable.",
                code="resource_bootstrap_file_not_found",
                context={"path": str(self._path)},
            )
        suffix = self._path.suffix.casefold()
        if suffix in {".xlsx", ".xlsm"}:
            return self._list_xlsx()
        if suffix == ".csv":
            return self._list_csv()
        raise ApplicationOperationError(
            "Le format de bootstrap des ressources doit être XLSX, XLSM ou CSV.",
            code="resource_bootstrap_file_type_unsupported",
            context={"suffix": suffix},
        )
