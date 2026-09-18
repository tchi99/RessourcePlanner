from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Mapping

from ...application.errors import ApplicationOperationError
from ...application.task_catalog import TaskCatalogItem, TaskCatalogSourcePort
from .excel_project_source import _load_erp_workbook


_REQUIRED_COLUMNS = ("ID tâche", "Description", "ID projet", "Statut")


def _text(value: object) -> str:
    return str(value or "").strip()


def _optional_text(value: object) -> str | None:
    normalized = _text(value)
    return normalized or None


def _identifier(value: object) -> str:
    if isinstance(value, bool):
        return _text(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return _text(value)


def _optional_bool(value: object) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = _text(value).casefold()
    if normalized in {"1", "true", "vrai", "oui", "yes", "y"}:
        return True
    if normalized in {"0", "false", "faux", "non", "no", "n"}:
        return False
    return None


def _optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).strip().replace("%", "").replace(",", "."))
    except (TypeError, ValueError):
        return None


def _optional_datetime(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    raw = _text(value)
    for candidate in (raw, raw.replace("Z", "+00:00")):
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            pass
    return None


def _active_from_status(value: object) -> bool:
    return _text(value).casefold() in {"actif", "active", "ouvert", "open"}


def _header_indexes(header: Iterable[object]) -> dict[str, int]:
    indexes: dict[str, int] = {}
    for index, value in enumerate(header):
        label = _text(value)
        if label and label not in indexes:
            indexes[label] = index
    missing = [column for column in _REQUIRED_COLUMNS if column not in indexes]
    if missing:
        raise ApplicationOperationError(
            "L'export ERP des tâches ne contient pas toutes les colonnes requises.",
            code="erp_task_catalog_headers_invalid",
            context={"missing_columns": missing},
        )
    return indexes


def _mapping_value(row: Mapping[str, object], *names: str) -> object | None:
    for name in names:
        if name in row:
            return row[name]
    return None


def _item_from_mapping(row: Mapping[str, object], *, row_number: int) -> TaskCatalogItem:
    project_number = _identifier(_mapping_value(row, "ID projet"))
    code = _identifier(_mapping_value(row, "ID tâche"))
    label = _text(_mapping_value(row, "Description"))
    status = _text(_mapping_value(row, "Statut")) or "Actif"

    if not project_number or not code or not label:
        raise ApplicationOperationError(
            "Une ligne de l'export ERP contient une tâche incomplète.",
            code="erp_task_catalog_row_invalid",
            context={
                "row": row_number,
                "has_project_id": bool(project_number),
                "has_task_id": bool(code),
                "has_description": bool(label),
            },
        )

    return TaskCatalogItem(
        project_number=project_number,
        code=code,
        label=label,
        status=status,
        active=_active_from_status(status),
        billing_rule=_optional_text(_mapping_value(row, "Règle de facturation")),
        allocation_rule=_optional_text(_mapping_value(row, "Règle de répartition")),
        completion_percent=_optional_float(_mapping_value(row, "Complété (%)")),
        erp_created_at=_optional_datetime(_mapping_value(row, "Créé le")),
        branch=_optional_text(_mapping_value(row, "Succursale")),
        approver_name=_optional_text(
            _mapping_value(row, "Nom de l’employé", "Nom de l'employé")
        ),
        cv_enabled=_optional_bool(_mapping_value(row, "CV")),
        time_entry_enabled=_optional_bool(_mapping_value(row, "Saisie des heures")),
        expenses_enabled=_optional_bool(_mapping_value(row, "Dépenses")),
    )


def _validate_duplicates(items: Iterable[TaskCatalogItem]) -> tuple[TaskCatalogItem, ...]:
    result: list[TaskCatalogItem] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        if item.external_key in seen:
            raise ApplicationOperationError(
                "La même tâche ERP apparaît plus d'une fois pour le même projet.",
                code="erp_task_catalog_duplicate_key",
                context={
                    "project_number": item.project_number,
                    "task_code": item.code,
                },
            )
        seen.add(item.external_key)
        result.append(item)
    return tuple(result)


class ErpTaskCatalogFileSource(TaskCatalogSourcePort):
    """Temporary XLSX/CSV source matching the real ERP task export."""

    def __init__(self, path: str | Path, *, sheet_name: str = "Données") -> None:
        self._path = Path(path)
        self._sheet_name = sheet_name

    @property
    def path(self) -> Path:
        return self._path

    def _list_xlsx(self) -> tuple[TaskCatalogItem, ...]:
        try:
            workbook = _load_erp_workbook(self._path)
        except (OSError, TypeError, ValueError) as exc:
            raise ApplicationOperationError(
                "Impossible d'ouvrir l'export ERP des tâches.",
                code="erp_task_catalog_file_invalid",
                context={"path": str(self._path)},
            ) from exc

        try:
            if self._sheet_name not in workbook.sheetnames:
                raise ApplicationOperationError(
                    f"La feuille '{self._sheet_name}' est absente de l'export ERP des tâches.",
                    code="erp_task_catalog_sheet_missing",
                    context={"sheet": self._sheet_name},
                )
            worksheet = workbook[self._sheet_name]
            rows = worksheet.iter_rows(values_only=True)
            header = next(rows, None)
            if header is None:
                raise ApplicationOperationError(
                    "La feuille des tâches ERP est vide.",
                    code="erp_task_catalog_sheet_empty",
                    context={"sheet": self._sheet_name},
                )
            indexes = _header_indexes(header)
            items: list[TaskCatalogItem] = []
            for row_number, values in enumerate(rows, start=2):
                if not any(value not in (None, "") for value in values):
                    continue
                mapped = {
                    name: values[index] if index < len(values) else None
                    for name, index in indexes.items()
                }
                # Preserve every optional column that is present in the real export.
                for name in (
                    "Règle de facturation",
                    "Règle de répartition",
                    "Complété (%)",
                    "Créé le",
                    "Succursale",
                    "Nom de l’employé",
                    "Nom de l'employé",
                    "CV",
                    "Saisie des heures",
                    "Dépenses",
                ):
                    if name in indexes:
                        index = indexes[name]
                        mapped[name] = values[index] if index < len(values) else None
                items.append(_item_from_mapping(mapped, row_number=row_number))
            return _validate_duplicates(items)
        finally:
            workbook.close()

    def _list_csv(self) -> tuple[TaskCatalogItem, ...]:
        raw: str | None = None
        for encoding in ("utf-8-sig", "cp1252"):
            try:
                raw = self._path.read_text(encoding=encoding)
                break
            except UnicodeDecodeError:
                continue
        if raw is None:
            raise ApplicationOperationError(
                "Impossible de décoder l'export CSV des tâches ERP.",
                code="erp_task_catalog_file_invalid",
                context={"path": str(self._path)},
            )
        try:
            dialect = csv.Sniffer().sniff(raw[:8192], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(raw.splitlines(), dialect=dialect)
        if reader.fieldnames is None:
            raise ApplicationOperationError(
                "L'export CSV des tâches ERP est vide.",
                code="erp_task_catalog_sheet_empty",
                context={"path": str(self._path)},
            )
        _header_indexes(reader.fieldnames)
        items = [
            _item_from_mapping(row, row_number=row_number)
            for row_number, row in enumerate(reader, start=2)
            if any(_text(value) for value in row.values())
        ]
        return _validate_duplicates(items)

    def list_tasks(self) -> tuple[TaskCatalogItem, ...]:
        if not self._path.is_file():
            raise ApplicationOperationError(
                "Le fichier d'export ERP des tâches est introuvable.",
                code="erp_task_catalog_file_not_found",
                context={"path": str(self._path)},
            )
        suffix = self._path.suffix.casefold()
        if suffix in {".xlsx", ".xlsm"}:
            return self._list_xlsx()
        if suffix == ".csv":
            return self._list_csv()
        raise ApplicationOperationError(
            "Le format d'export des tâches doit être XLSX, XLSM ou CSV.",
            code="erp_task_catalog_file_type_unsupported",
            context={"suffix": suffix},
        )
