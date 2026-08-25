from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import nullcontext
from datetime import datetime
from typing import Any, ContextManager

from .command_ports import ApprovedDemandSyncPort, PlanningCommandPort
from .repository_ports import DemandRepositoryPort


BUSINESS_DEMAND_FIELDS = frozenset(
    {
        "NumeroProjet",
        "NomProjet",
        "Client",
        "ChargeProjet",
        "TypeDemande",
        "Priorite",
        "Confirmation",
        "DateDebutSouhaitee",
        "DateFinSouhaitee",
        "Description",
        "SiteClient",
        "Lieu",
        "NombreRessources",
        "CompetencesRequises",
        "TempsEstimeHeures",
        "TempsEstimeJours",
        "TechnicienPropose",
    }
)

WORKFLOW_OWNED_CREATION_FIELDS = frozenset(
    {
        "NoDemande",
        "Statut",
        "DateCreation",
        "DateModification",
        "ApprouvePar",
        "DateApprobation",
        "CommentaireApprobation",
    }
)


class DemandService:
    """Application service for the workforce-demand lifecycle.

    Persistence, approved-demand synchronization and planning are explicit ports.
    The service contains workflow orchestration only and is independent from Excel,
    NiceGUI, xlwings and historical V1 modules.
    """

    def __init__(
        self,
        demands: DemandRepositoryPort,
        planning: PlanningCommandPort,
        approved_sync: ApprovedDemandSyncPort,
        *,
        current_user: str = "",
        batch: Callable[[str], ContextManager[Any]] | None = None,
    ) -> None:
        self._demands = demands
        self._planning = planning
        self._approved_sync = approved_sync
        self._current_user = str(current_user or "")
        self._batch = batch

    def _context(self, label: str) -> ContextManager[Any]:
        return self._batch(label) if self._batch is not None else nullcontext()

    def create(self, data: Mapping[str, Any], *, submit: bool = False) -> str:
        values = dict(data)
        for field in WORKFLOW_OWNED_CREATION_FIELDS:
            values.pop(field, None)

        if not str(values.get("NumeroProjet") or "").strip():
            raise ValueError("Le projet est requis.")
        if values.get("DateDebutSouhaitee") in (None, ""):
            raise ValueError("La date de début est requise.")

        with self._context("create demand"):
            number = self._demands.create(values, submit=bool(submit))

        normalized = str(number or "").strip()
        if not normalized:
            raise RuntimeError("La création de la demande n'a retourné aucun numéro.")
        return normalized

    def modify(
        self,
        number: str,
        updates: Mapping[str, Any],
        comment: str = "Demande modifiée dans l'application",
    ) -> bool:
        existing = self._demands.get(number)
        if existing is None:
            raise KeyError(f"Demande {number} introuvable")

        data = dict(updates)
        reapproval_required = (
            existing.status == "En planification"
            and bool(BUSINESS_DEMAND_FIELDS.intersection(data))
        )

        audit_comment = str(comment or "").strip()
        if reapproval_required:
            data["Statut"] = "Soumise"
            data["ApprouvePar"] = None
            data["DateApprobation"] = None
            data["CommentaireApprobation"] = (
                "Demande modifiée après approbation — nouvelle approbation requise"
            )
            suffix = "Nouvelle approbation requise; la planification existante est conservée"
            audit_comment = f"{audit_comment} · {suffix}" if audit_comment else suffix

        with self._context("modify demand"):
            self._demands.update(
                number,
                data,
                action="Modification",
                comment=audit_comment,
            )
        return reapproval_required

    def submit(self, number: str) -> None:
        with self._context("submit demand"):
            self._demands.update(
                number,
                {"Statut": "Soumise"},
                action="Soumission",
                comment="Demande soumise pour approbation",
            )

    def approve(self, number: str, comment: str = "") -> dict[str, Any]:
        with self._context("approve demand"):
            self._demands.update(
                number,
                {
                    "Statut": "En planification",
                    "ApprouvePar": self._current_user,
                    "DateApprobation": datetime.now(),
                    "CommentaireApprobation": comment,
                },
                action="Approbation",
                comment=comment or "Demande approuvée",
            )
            self._approved_sync.sync_approved(number)
            summary = self._planning.rebuild()
        return dict(summary)

    def request_correction(self, number: str, comment: str) -> None:
        reason = str(comment or "").strip()
        if not reason:
            raise ValueError("Un commentaire de correction est requis.")
        with self._context("request demand correction"):
            self._demands.update(
                number,
                {
                    "Statut": "À corriger",
                    "CommentaireApprobation": reason,
                },
                action="Retour pour correction",
                comment=reason,
            )

    def cancel(self, number: str) -> None:
        with self._context("cancel demand"):
            self._demands.update(
                number,
                {"Statut": "Annulée"},
                action="Annulation",
                comment="Demande annulée",
            )
