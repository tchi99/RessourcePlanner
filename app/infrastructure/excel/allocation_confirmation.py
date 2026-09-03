from __future__ import annotations

from importlib import import_module
from typing import Any

from ...domain.confirmation import normalize_confirmation


ALLOCATION_CONFIRMATION_FIELD = "Confirmation"


def register_allocation_confirmation_header() -> None:
    """Register the optional V1 column before any allocation rebuild can rewrite rows."""

    v14_engine = import_module("app.v14_engine")
    if ALLOCATION_CONFIRMATION_FIELD not in v14_engine.ALLOCATION_HEADERS:
        v14_engine.ALLOCATION_HEADERS.append(ALLOCATION_CONFIRMATION_FIELD)


def normalize_optional_confirmation(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return normalize_confirmation(text)


def ensure_allocation_confirmation_field(repository: Any) -> None:
    """Ensure the transitional Excel allocation table can persist a shift override.

    SQL remains the target authority. This V1 bridge adds one optional column only so
    the current NiceGUI editor can expose the confirmation capability that already
    exists in the application/API model.
    """

    marker = str(getattr(repository, "path", "") or "")
    if getattr(repository, "_allocation_confirmation_ready_path", None) == marker:
        return

    register_allocation_confirmation_header()
    v14_engine = import_module("app.v14_engine")
    v15_engine = import_module("app.v15_engine")
    v15_engine.ensure_v15_sheets(repository)

    repository._ensure_sheet_table(
        v14_engine.ALLOCATION_SHEET,
        v14_engine.ALLOCATION_HEADERS,
        v14_engine.ALLOCATION_TABLE,
    )
    repository.save()
    repository._allocation_confirmation_ready_path = marker


def set_allocation_confirmation(
    repository: Any,
    allocation_id: str,
    confirmation: object,
) -> None:
    """Persist an explicit V1 shift confirmation override after the guarded mutation."""

    value = normalize_optional_confirmation(confirmation)
    if value is None:
        return

    ensure_allocation_confirmation_field(repository)
    v14_engine = import_module("app.v14_engine")
    v15_engine = import_module("app.v15_engine")
    allocation = v15_engine.allocation_by_id(repository, allocation_id)
    if not allocation:
        raise KeyError(f"Allocation {allocation_id} introuvable")

    with repository._lock:
        sheet = repository._book().sheets[v14_engine.ALLOCATION_SHEET]
        header_map = v15_engine._allocation_header_map(repository)
        column = header_map.get(ALLOCATION_CONFIRMATION_FIELD)
        if not column:
            raise RuntimeError("La colonne Confirmation du quart est introuvable.")
        sheet.range((int(allocation["_row"]), column)).value = value
        repository.save()


# command_adapters imports this module while the runtime composition is assembled,
# before the V1 planning installers are executed. Registering the header here ensures
# a restart cannot rebuild allocation rows with a shorter schema and detach an
# existing confirmation value from its shift.
register_allocation_confirmation_header()
