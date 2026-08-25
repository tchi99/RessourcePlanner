from __future__ import annotations

from collections.abc import Mapping

from .excel_cutover import CutoverReader


def _text(value: object) -> str:
    return str(value or "").strip()


def _legacy_reference(value: object) -> str:
    text = _text(value)
    if not text:
        return ""
    try:
        number = float(text.replace(",", "."))
    except (TypeError, ValueError):
        return text
    return str(int(number)) if number.is_integer() else text


def extract_demand_work_package_links(reader: CutoverReader) -> Mapping[str, str]:
    """Return NoDemande -> stable effort id (or historical source row fallback).

    V1.8 backfills ``SourceEffortID`` from ``SourceEffortRow``. The fallback remains
    supported so a frozen workbook that predates the backfill can still be migrated
    without inventing a WorkPackage link.
    """

    result: dict[str, str] = {}
    for row in reader.records("DemandesMO", "NoDemande"):
        number = _text(row.get("NoDemande"))
        if not number:
            continue
        reference = _legacy_reference(
            row.get("SourceEffortID") or row.get("SourceEffortRow")
        )
        if reference:
            result[number] = reference
    return result
