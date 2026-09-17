from __future__ import annotations

from pathlib import Path
from typing import Iterable

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from ...application import ApplicationOperationError, ExternalProjectRecord, ProjectSourcePort


_REQUIRED_COLUMNS = (
    "ID projet",
    "Statut",
    "Description",
    "Nom du client",
    "Gestionnaire de projet",
)


def _text(value: object) -> str:
    return str(value or "").strip()


def _optional_text(value: object) -> str | None:
    text = _text(value)
    return text or None


def _project_number(value: object) -> str:
    if isinstance(value, bool):
        return _text(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return _text(value)


class ErpExcelProjectSource(ProjectSourcePort):
    """Project source for the manual ERP XLSX export used before live ERP connectivity."""

    def __init__(self, path: str | Path, *, sheet_name: str = "Données") -> None:
        self._path = Path(path)
        self._sheet_name = sheet_name

    @property
    def path(self) -> Path:
        return self._path

    def _header_indexes(self, header: Iterable[object]) -> dict[str, int]:
        indexes: dict[str, int] = {}
        for index, value in enumerate(header):
            label = _text(value)
            if label and label not in indexes:
                indexes[label] = index

        missing = [column for column in _REQUIRED_COLUMNS if column not in indexes]
        if missing:
            raise ApplicationOperationError(
                "Le fichier d'export ERP ne contient pas toutes les colonnes requises.",
                code="erp_excel_project_headers_invalid",
                context={"missing_columns": missing, "sheet": self._sheet_name},
            )
        return indexes

    @staticmethod
    def _value(row: tuple[object, ...], index: int) -> object | None:
        return row[index] if index < len(row) else None

    def list_projects(self) -> tuple[ExternalProjectRecord, ...]:
        if not self._path.is_file():
            raise ApplicationOperationError(
                "Le fichier d'export ERP est introuvable.",
                code="erp_excel_project_file_not_found",
                context={"path": str(self._path)},
            )

        try:
            workbook = load_workbook(self._path, read_only=True, data_only=True)
        except (OSError, InvalidFileException, ValueError) as exc:
            raise ApplicationOperationError(
                "Impossible d'ouvrir le fichier d'export ERP.",
                code="erp_excel_project_file_invalid",
                context={"path": str(self._path)},
            ) from exc

        try:
            if self._sheet_name not in workbook.sheetnames:
                raise ApplicationOperationError(
                    f"La feuille '{self._sheet_name}' est absente du fichier d'export ERP.",
                    code="erp_excel_project_sheet_missing",
                    context={"sheet": self._sheet_name},
                )

            worksheet = workbook[self._sheet_name]
            rows = worksheet.iter_rows(values_only=True)
            header = next(rows, None)
            if header is None:
                raise ApplicationOperationError(
                    "La feuille des projets ERP est vide.",
                    code="erp_excel_project_sheet_empty",
                    context={"sheet": self._sheet_name},
                )
            indexes = self._header_indexes(header)

            result: list[ExternalProjectRecord] = []
            seen_numbers: set[str] = set()
            for row_number, row in enumerate(rows, start=2):
                if not any(value not in (None, "") for value in row):
                    continue

                number = _project_number(self._value(row, indexes["ID projet"]))
                name = _text(self._value(row, indexes["Description"]))
                if not number or not name:
                    raise ApplicationOperationError(
                        "Une ligne de l'export ERP contient un projet incomplet.",
                        code="erp_excel_project_row_invalid",
                        context={
                            "row": row_number,
                            "has_project_id": bool(number),
                            "has_description": bool(name),
                        },
                    )
                if number in seen_numbers:
                    raise ApplicationOperationError(
                        "Le même numéro de projet apparaît plus d'une fois dans l'export ERP.",
                        code="erp_excel_project_duplicate_number",
                        context={"row": row_number, "project_number": number},
                    )
                seen_numbers.add(number)

                result.append(
                    ExternalProjectRecord(
                        # The XLSX export exposes ProjectID, not Acumatica's REST row id.
                        # Keep the external id unbound so a later live ERP sync can adopt
                        # the same local project by number and attach the real ERP id.
                        external_id=None,
                        number=number,
                        name=name,
                        client=_optional_text(self._value(row, indexes["Nom du client"])),
                        project_manager_name=_optional_text(
                            self._value(row, indexes["Gestionnaire de projet"])
                        ),
                        status=_text(self._value(row, indexes["Statut"])) or "Actif",
                    )
                )
            return tuple(result)
        finally:
            workbook.close()
