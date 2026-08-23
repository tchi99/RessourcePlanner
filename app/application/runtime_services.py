from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime
from importlib import import_module
from typing import Any, Mapping

from .demand_service import DemandService
from .planning_service import PlanningService
from .segment_service import SegmentService


def _runtime_rebuild(repository: Any):
    """Resolve the currently installed planning alias only when executed."""
    v15_engine = import_module("app.v15_engine")
    return v15_engine.rebuild_allocations(repository)


def _load_demand_record(repository: Any, number: str) -> Mapping[str, Any] | None:
    return next(
        (
            row
            for row in repository.demands()
            if str(row.get("NoDemande") or "") == str(number)
        ),
        None,
    )


def _create_demand_record(
    repository: Any,
    values: Mapping[str, Any],
    submit: bool,
) -> str:
    return str(repository.create_demand(dict(values), submit=submit))


def _modify_demand_record(
    repository: Any,
    number: str,
    updates: Mapping[str, Any],
    comment: str,
) -> None:
    repository.update_demand(
        number,
        dict(updates),
        action="Modification",
        comment=comment,
    )


def _submit_demand_record(repository: Any, number: str) -> None:
    repository.update_demand(
        number,
        {"Statut": "Soumise"},
        action="Soumission",
        comment="Demande soumise pour approbation",
    )


def _approve_demand_record(repository: Any, number: str, comment: str) -> None:
    """Persist only the approval decision.

    Approval workflow orchestration belongs to ``DemandService``: this adapter writes
    the decision only, while the service owns requirement synchronization and the
    single planning rebuild that follows approval.
    """
    repository.update_demand(
        number,
        {
            "Statut": "En planification",
            "ApprouvePar": repository.current_user,
            "DateApprobation": datetime.now(),
            "CommentaireApprobation": comment,
        },
        action="Approbation",
        comment=comment or "Demande approuvée",
    )


def _request_correction_record(repository: Any, number: str, comment: str) -> None:
    repository.update_demand(
        number,
        {
            "Statut": "À corriger",
            "CommentaireApprobation": comment,
        },
        action="Retour pour correction",
        comment=comment,
    )


def _cancel_demand_record(repository: Any, number: str) -> None:
    repository.update_demand(
        number,
        {"Statut": "Annulée"},
        action="Annulation",
        comment="Demande annulée",
    )


def _sync_approved_demand(repository: Any, number: str) -> None:
    """Synchronize operational requirements with the newly approved version."""
    refinements = import_module("app.v15_refinements")
    demand = _load_demand_record(repository, number)
    if demand is None:
        raise KeyError(f"Demande {number} introuvable après approbation")
    refinements._sync_segments_to_approved_demand(repository, demand)


def _create_segment_record(repository: Any, values: Mapping[str, Any]) -> str:
    """Resolve the fully composed V1 segment writer at execution time.

    The runtime alias intentionally remains lazy so V1 compatibility wrappers such as
    approved-location projection keep applying until the Excel repository is replaced.
    """
    v13 = import_module("app.v13")
    return str(v13.add_segment(repository, dict(values)))


def _update_segment_record(
    repository: Any,
    segment_id: str,
    updates: Mapping[str, Any],
) -> None:
    v13 = import_module("app.v13")
    v13.update_segment(repository, segment_id, dict(updates))


def _runtime_batch(repository: Any, label: str):
    factory = getattr(repository, "batch_update", None)
    if callable(factory):
        return factory(label)
    return nullcontext()


def planning_service(repository: Any) -> PlanningService[Any]:
    """Build the runtime planning service against the authoritative engine alias.

    Engine import and lookup are deliberately lazy. Lightweight CI can import the
    application layer without NiceGUI, while the running application resolves the
    authoritative ``v15_engine.rebuild_allocations`` alias only when a rebuild runs.
    """
    return PlanningService(
        repository,
        rebuild_planning=_runtime_rebuild,
    )


def demand_service(repository: Any) -> DemandService[Any]:
    """Build the runtime demand service against today's Excel/V1 adapters.

    This is the migration seam between the current Excel/V1.x implementation and the
    future repository/API architecture. The service owns demand creation,
    edit/reapproval policy and lifecycle workflow ordering while these adapters
    translate operations to the current storage model.
    """
    return DemandService(
        repository,
        load_record=_load_demand_record,
        create_record=_create_demand_record,
        modify_record=_modify_demand_record,
        submit_record=_submit_demand_record,
        approve_record=_approve_demand_record,
        request_correction_record=_request_correction_record,
        cancel_record=_cancel_demand_record,
        sync_approved_demand=_sync_approved_demand,
        rebuild_planning=_runtime_rebuild,
        batch=_runtime_batch,
    )


def segment_service(repository: Any) -> SegmentService[Any]:
    """Build the segment workflow boundary against the composed V1 adapters."""
    return SegmentService(
        repository,
        create_record=_create_segment_record,
        update_record=_update_segment_record,
        rebuild_planning=_runtime_rebuild,
    )
