from __future__ import annotations

from typing import Any

from nicegui import ui

from .application.allocation_service import AllocationService
from .infrastructure.excel.command_adapters import (
    capture_excel_allocation_commands,
    excel_allocation_commands,
    install_excel_allocation_service_entrypoints,
)


_installed = False


def _service(repository: Any) -> AllocationService:
    return AllocationService(excel_allocation_commands(repository))


def _create_manual_via_service(
    repository: Any,
    segment_id: str,
    technician: str,
    day_value: Any,
    hours_value: Any,
    hors_horaire: bool = False,
    note: str = "",
    confirmation: str | None = None,
) -> str:
    return _service(repository).create_manual(
        segment_id,
        technician,
        day_value,
        hours_value,
        hors_horaire,
        note,
        confirmation,
    )


def _update_manual_via_service(
    repository: Any,
    identifier: str,
    technician: str,
    day_value: Any,
    hours_value: Any,
    hors_horaire: bool = False,
    note: str = "",
    confirmation: str | None = None,
) -> None:
    _service(repository).update_manual(
        identifier,
        technician,
        day_value,
        hours_value,
        hors_horaire,
        note,
        confirmation,
    )


def _release_manual_via_service(repository: Any, identifier: str) -> None:
    _service(repository).release_manual(identifier)


def _delete_manual_via_service(repository: Any, identifier: str) -> None:
    _service(repository).delete_manual(identifier)


def _assign_segment_via_service(
    self: Any,
    segment: dict[str, Any],
    technician: str,
    dialog: Any,
) -> None:
    try:
        segment_id = str(segment.get("IDSegment") or "")
        summary = _service(self.repo).assign_segment(segment_id, technician)
        dialog.close()
        message = f"{segment_id} assigné à {technician}"
        if summary.get("unallocated_hours", 0) > 0:
            message += (
                f" · {summary['unallocated_hours']:g} h nécessitent du hors horaire"
            )
        self._after_write(message)
    except Exception as exc:
        ui.notify(str(exc), type="negative")


def install_allocation_service_ui() -> None:
    """Bind V1 UI entry points to AllocationService through an Excel command port."""

    global _installed
    if _installed:
        return

    # Operational runtime guards are installed earlier. Capture those guarded
    # functions once, before replacing the historical entrypoints with service calls.
    capture_excel_allocation_commands()
    install_excel_allocation_service_entrypoints(
        create_manual=_create_manual_via_service,
        update_manual=_update_manual_via_service,
        release_manual=_release_manual_via_service,
        delete_manual=_delete_manual_via_service,
        assign_segment=_assign_segment_via_service,
    )
    _installed = True
