from __future__ import annotations

from typing import Any, Callable

from nicegui import ui

from . import v13, v15_engine, v16
from .application.allocation_service import AllocationService


CreateFn = Callable[[Any, str, str, Any, Any, bool, str], str]
UpdateFn = Callable[[Any, str, str, Any, Any, bool, str], None]
IdFn = Callable[[Any, str], None]


_legacy_create: CreateFn | None = None
_legacy_update: UpdateFn | None = None
_legacy_release: IdFn | None = None
_legacy_delete: IdFn | None = None


def _assign_segment_record(repository: Any, segment_id: str, technician: str):
    """Translate assignment intent to today's segment store and active engine.

    ``v15_engine.rebuild_allocations`` is resolved when the action executes, not when
    this installer runs. The planning cutover therefore remains authoritative after it
    replaces that alias with legacy/guarded-pure/pure mode.
    """
    v13.update_segment(
        repository,
        segment_id,
        {"Technicien": technician, "Statut": "Planifié"},
    )
    return v15_engine.rebuild_allocations(repository)


def _service(repository: Any) -> AllocationService[Any]:
    assert _legacy_create is not None
    assert _legacy_update is not None
    assert _legacy_release is not None
    assert _legacy_delete is not None
    return AllocationService(
        repository,
        create_manual_record=_legacy_create,
        update_manual_record=_legacy_update,
        release_manual_record=_legacy_release,
        delete_manual_record=_legacy_delete,
        assign_segment_record=_assign_segment_record,
    )


def _create_manual_via_service(
    repository: Any,
    segment_id: str,
    technician: str,
    day_value: Any,
    hours_value: Any,
    hors_horaire: bool = False,
    note: str = "",
) -> str:
    return _service(repository).create_manual(
        segment_id,
        technician,
        day_value,
        hours_value,
        hors_horaire,
        note,
    )


def _update_manual_via_service(
    repository: Any,
    identifier: str,
    technician: str,
    day_value: Any,
    hours_value: Any,
    hors_horaire: bool = False,
    note: str = "",
) -> None:
    _service(repository).update_manual(
        identifier,
        technician,
        day_value,
        hours_value,
        hors_horaire,
        note,
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
    """Bind historical operational UI entry points to AllocationService.

    This is a transitional #15 seam. The dialogs remain in the V1.x renderer for now,
    but their write paths no longer own allocation workflow directly. The original V1
    persistence functions are captured as adapters so behavior stays unchanged.
    """
    global _legacy_create, _legacy_update, _legacy_release, _legacy_delete

    if getattr(v15_engine, "_allocation_service_ui_installed", False):
        return

    _legacy_create = v15_engine.create_manual_allocation
    _legacy_update = v15_engine.update_manual_allocation
    _legacy_release = v15_engine.release_manual_allocation
    _legacy_delete = v15_engine.delete_manual_allocation

    v15_engine.create_manual_allocation = _create_manual_via_service
    v15_engine.update_manual_allocation = _update_manual_via_service
    v15_engine.release_manual_allocation = _release_manual_via_service
    v15_engine.delete_manual_allocation = _delete_manual_via_service
    v16._assign_segment = _assign_segment_via_service
    v15_engine._allocation_service_ui_installed = True
