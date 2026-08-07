from __future__ import annotations

import time
from typing import Any

from . import features
from .excel_repository import MASTER_SHEETS


def apply_runtime_optimizations() -> None:
    """Keep availability rendering responsive when Excel is accessed through COM.

    The feature module intentionally works directly against the workbook. This patch avoids
    re-formatting/saving the Disponibilites sheet for every calendar cell and keeps a very short
    read cache so one planning render only crosses the Excel COM boundary once.
    """

    if getattr(features, "_runtime_optimizations_installed", False):
        return

    def ensure_availability_sheet(repo: Any) -> None:
        MASTER_SHEETS.add(features.AVAILABILITY_SHEET)
        try:
            repo._book().sheets[features.AVAILABILITY_SHEET]
            return
        except Exception:
            repo._ensure_sheet_table(
                features.AVAILABILITY_SHEET,
                features.AVAILABILITY_HEADERS,
                features.AVAILABILITY_TABLE,
            )
            repo.save()

    features._ensure_availability_sheet = ensure_availability_sheet

    original_records = features.availability_records
    original_add = features.add_availability
    original_delete = features.delete_availability

    def clear_cache(repo: Any) -> None:
        if hasattr(repo, "_availability_records_cache"):
            delattr(repo, "_availability_records_cache")

    def cached_records(repo: Any):
        now = time.monotonic()
        cache = getattr(repo, "_availability_records_cache", None)
        if cache and now - cache[0] < 0.75:
            return cache[1]
        rows = original_records(repo)
        repo._availability_records_cache = (now, rows)
        return rows

    def add_availability(repo: Any, values: dict[str, Any]) -> str:
        result = original_add(repo, values)
        clear_cache(repo)
        return result

    def delete_availability(repo: Any, row_number: int) -> None:
        original_delete(repo, row_number)
        clear_cache(repo)

    features.availability_records = cached_records
    features.add_availability = add_availability
    features.delete_availability = delete_availability
    features._runtime_optimizations_installed = True
