from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime
from importlib import import_module
from typing import Any

from .demand_service import DemandService
from .planning_service import PlanningService


def _runtime_rebuild(repository: Any):
    """Resolve the currently installed planning alias only when executed."""
    v15_engine = import_module("app.v15_engine")
    return v15_engine.rebuild_allocations(repository)


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
    demand = next(
        (
            row
            for row in repository.demands()
            if str(row.get("NoDemande") or "") == str(number)
        ),
        None,
    )
    if demand is None:
        raise KeyError(f"Demande {number} introuvable après approbation")
    refinements._sync_segments_to_approved_demand(repository, demand)


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
    future repository/API architecture. The service owns lifecycle workflow ordering
    while these adapters translate operations to the current storage model.
    """
    return DemandService(
        repository,
        submit_record=_submit_demand_record,
        approve_record=_approve_demand_record,
        request_correction_record=_request_correction_record,
        cancel_record=_cancel_demand_record,
        sync_approved_demand=_sync_approved_demand,
        rebuild_planning=_runtime_rebuild,
        batch=_runtime_batch,
    )
