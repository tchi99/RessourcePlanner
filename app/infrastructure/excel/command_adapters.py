from __future__ import annotations

from collections.abc import Callable, Mapping
from importlib import import_module
from typing import Any

from ...application.command_ports import (
    AllocationCommandPort,
    ApprovedDemandSyncPort,
    PlanningCommandPort,
)
from .demand_repository import ExcelDemandRepository


CreateAllocationFn = Callable[..., str]
UpdateAllocationFn = Callable[..., None]
AllocationIdFn = Callable[[Any, str], None]
ALLOCATION_CONFIRMATION_FIELD = "Confirmation"

_captured_allocation_functions: tuple[
    CreateAllocationFn,
    UpdateAllocationFn,
    AllocationIdFn,
    AllocationIdFn,
] | None = None


def _ensure_allocation_confirmation_field(repository: Any) -> None:
    """Append the V1 shift confirmation override without relabelling old columns."""

    marker = str(getattr(repository, "path", "") or "")
    if getattr(repository, "_shift_confirmation_ready_path", None) == marker:
        return

    v14_engine = import_module("app.v14_engine")
    if ALLOCATION_CONFIRMATION_FIELD not in v14_engine.ALLOCATION_HEADERS:
        v14_engine.ALLOCATION_HEADERS.append(ALLOCATION_CONFIRMATION_FIELD)
    repository._ensure_sheet_table(
        v14_engine.ALLOCATION_SHEET,
        v14_engine.ALLOCATION_HEADERS,
        v14_engine.ALLOCATION_TABLE,
    )
    repository.save()
    repository._shift_confirmation_ready_path = marker


def _set_allocation_confirmation(
    repository: Any,
    allocation_id: str,
    confirmation: str | None,
) -> None:
    """Persist a nullable V1 override; blank means inherit from the upper level."""

    _ensure_allocation_confirmation_field(repository)
    v14_engine = import_module("app.v14_engine")
    v15_engine = import_module("app.v15_engine")
    allocation = v15_engine.allocation_by_id(repository, allocation_id)
    if allocation is None:
        raise KeyError(f"Allocation {allocation_id} introuvable")
    header_map = v15_engine._allocation_header_map(repository)
    column = header_map.get(ALLOCATION_CONFIRMATION_FIELD)
    if not column:
        raise RuntimeError("La colonne Confirmation du quart n'a pas pu être créée.")
    value = str(confirmation or "").strip() or None
    with repository._lock:
        sheet = repository._book().sheets[v14_engine.ALLOCATION_SHEET]
        sheet.range((int(allocation["_row"]), column)).value = value
        repository.save()


class ExcelPlanningCommandAdapter(PlanningCommandPort):
    """Excel/V1 implementation of the authoritative planning command."""

    def __init__(self, repository: Any) -> None:
        self._repository = repository

    def rebuild(self) -> Mapping[str, Any]:
        # Resolve at execution time so the final pure-engine cutover alias wins.
        v15_engine = import_module("app.v15_engine")
        return v15_engine.rebuild_allocations(self._repository)


class ExcelAllocationCommandAdapter(AllocationCommandPort):
    """Excel/V1 implementation of manual shift and assignment commands."""

    def __init__(
        self,
        repository: Any,
        *,
        create_manual_record: CreateAllocationFn,
        update_manual_record: UpdateAllocationFn,
        release_manual_record: AllocationIdFn,
        delete_manual_record: AllocationIdFn,
    ) -> None:
        self._repository = repository
        self._create_manual_record = create_manual_record
        self._update_manual_record = update_manual_record
        self._release_manual_record = release_manual_record
        self._delete_manual_record = delete_manual_record

    def create_manual(
        self,
        segment_id: str,
        technician: str,
        day_value: Any,
        hours_value: Any,
        hors_horaire: bool = False,
        note: str = "",
        confirmation: str | None = None,
    ) -> str:
        identifier = str(
            self._create_manual_record(
                self._repository,
                segment_id,
                technician,
                day_value,
                hours_value,
                bool(hors_horaire),
                str(note or ""),
            )
        )
        if confirmation is not None:
            _set_allocation_confirmation(self._repository, identifier, confirmation)
        return identifier

    def update_manual(
        self,
        allocation_id: str,
        technician: str,
        day_value: Any,
        hours_value: Any,
        hors_horaire: bool = False,
        note: str = "",
        confirmation: str | None = None,
    ) -> None:
        self._update_manual_record(
            self._repository,
            allocation_id,
            technician,
            day_value,
            hours_value,
            bool(hors_horaire),
            str(note or ""),
        )
        if confirmation is not None:
            _set_allocation_confirmation(self._repository, allocation_id, confirmation)

    def release_manual(self, allocation_id: str) -> None:
        self._release_manual_record(self._repository, allocation_id)
        _set_allocation_confirmation(self._repository, allocation_id, None)

    def delete_manual(self, allocation_id: str) -> None:
        self._delete_manual_record(self._repository, allocation_id)

    def assign_segment(self, segment_id: str, technician: str) -> Mapping[str, Any]:
        # Keep the historical V1 assignment semantics behind the Excel adapter.
        v13 = import_module("app.v13")
        v15_engine = import_module("app.v15_engine")
        v13.update_segment(
            self._repository,
            segment_id,
            {"Technicien": technician, "Statut": "Planifié"},
        )
        return v15_engine.rebuild_allocations(self._repository)


class ExcelApprovedDemandSyncAdapter(ApprovedDemandSyncPort):
    """Excel compatibility adapter for approved Demand -> Segment synchronization."""

    def __init__(
        self,
        repository: Any,
        demands: ExcelDemandRepository | None = None,
    ) -> None:
        self._repository = repository
        self._demands = demands or ExcelDemandRepository(repository)

    def sync_approved(self, demand_number: str) -> None:
        demand = self._demands.raw_mapping(demand_number)
        if demand is None:
            raise KeyError(f"Demande {demand_number} introuvable après approbation")
        refinements = import_module("app.v15_refinements")
        refinements._sync_segments_to_approved_demand(self._repository, demand)


def capture_excel_allocation_commands() -> None:
    """Capture guarded V1 allocation functions before service entrypoints replace them."""

    global _captured_allocation_functions
    if _captured_allocation_functions is not None:
        return
    v15_engine = import_module("app.v15_engine")
    _captured_allocation_functions = (
        v15_engine.create_manual_allocation,
        v15_engine.update_manual_allocation,
        v15_engine.release_manual_allocation,
        v15_engine.delete_manual_allocation,
    )


def excel_allocation_commands(repository: Any) -> ExcelAllocationCommandAdapter:
    if _captured_allocation_functions is None:
        raise RuntimeError(
            "Les commandes d'allocation Excel ne sont pas encore capturées par le runtime."
        )
    create, update, release, delete = _captured_allocation_functions
    return ExcelAllocationCommandAdapter(
        repository,
        create_manual_record=create,
        update_manual_record=update,
        release_manual_record=release,
        delete_manual_record=delete,
    )


def install_excel_allocation_service_entrypoints(
    *,
    create_manual: CreateAllocationFn,
    update_manual: UpdateAllocationFn,
    release_manual: AllocationIdFn,
    delete_manual: AllocationIdFn,
    assign_segment: Callable[[Any, dict[str, Any], str, Any], None],
) -> None:
    """Keep V1 UI entrypoint mutation inside the Excel compatibility adapter."""

    v15_engine = import_module("app.v15_engine")
    v16 = import_module("app.v16")
    v15_engine.create_manual_allocation = create_manual
    v15_engine.update_manual_allocation = update_manual
    v15_engine.release_manual_allocation = release_manual
    v15_engine.delete_manual_allocation = delete_manual
    v16._assign_segment = assign_segment
    v15_engine._allocation_service_ui_installed = True
