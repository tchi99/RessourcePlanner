from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import nullcontext
from typing import Any, ContextManager, Generic, TypeVar


RepositoryT = TypeVar("RepositoryT")


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


class DemandService(Generic[RepositoryT]):
    """Application service for workforce-demand lifecycle workflows.

    The service owns orchestration and workflow-level validation only. Storage
    mutation, synchronization of approved operational requirements, planning rebuild
    and batching are injected by the composition layer so this module stays
    independent from NiceGUI, Excel, xlwings and versioned V1.x modules.
    """

    def __init__(
        self,
        repository: RepositoryT,
        *,
        load_record: Callable[[RepositoryT, str], Mapping[str, Any] | None],
        modify_record: Callable[[RepositoryT, str, Mapping[str, Any], str], None],
        submit_record: Callable[[RepositoryT, str], None],
        approve_record: Callable[[RepositoryT, str, str], None],
        request_correction_record: Callable[[RepositoryT, str, str], None],
        cancel_record: Callable[[RepositoryT, str], None],
        sync_approved_demand: Callable[[RepositoryT, str], None],
        rebuild_planning: Callable[[RepositoryT], Mapping[str, Any]],
        create_record: Callable[[RepositoryT, Mapping[str, Any], bool], str] | None = None,
        batch: Callable[[RepositoryT, str], ContextManager[Any]] | None = None,
    ) -> None:
        self._repository = repository
        self._load_record = load_record
        self._create_record = create_record
        self._modify_record = modify_record
        self._submit_record = submit_record
        self._approve_record = approve_record
        self._request_correction_record = request_correction_record
        self._cancel_record = cancel_record
        self._sync_approved_demand = sync_approved_demand
        self._rebuild_planning = rebuild_planning
        self._batch = batch

    def _context(self, label: str) -> ContextManager[Any]:
        return (
            self._batch(self._repository, label)
            if self._batch is not None
            else nullcontext()
        )

    def create(self, data: Mapping[str, Any], *, submit: bool = False) -> str:
        """Create a draft or submitted demand through the application boundary.

        Identity, status and approval metadata are storage/workflow-owned and cannot
        be injected by the UI. The current Excel adapter still generates the request
        number and creation audit entry; callers only express business data plus the
        intent to keep the demand as a draft or submit it immediately.
        """
        if self._create_record is None:
            raise RuntimeError("La création de demandes n'est pas configurée.")

        values = dict(data)
        for field in WORKFLOW_OWNED_CREATION_FIELDS:
            values.pop(field, None)

        if not str(values.get("NumeroProjet") or "").strip():
            raise ValueError("Le projet est requis.")
        if values.get("DateDebutSouhaitee") in (None, ""):
            raise ValueError("La date de début est requise.")

        with self._context("create demand"):
            number = self._create_record(self._repository, values, bool(submit))

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
        """Persist a demand edit and return whether reapproval became required.

        An approved demand remains the source of the active operational plan until a
        newly edited business version is approved. Therefore editing any business
        field while the request is ``En planification`` moves only the request back to
        ``Soumise`` and clears its approval metadata. Existing requirements and shifts
        are deliberately left untouched here.
        """
        existing = self._load_record(self._repository, number)
        if existing is None:
            raise KeyError(f"Demande {number} introuvable")

        data = dict(updates)
        reapproval_required = (
            str(existing.get("Statut") or "") == "En planification"
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
            self._modify_record(self._repository, number, data, audit_comment)
        return reapproval_required

    def submit(self, number: str) -> None:
        """Submit a draft/corrected demand for approval."""
        with self._context("submit demand"):
            self._submit_record(self._repository, number)

    def approve(self, number: str, comment: str = "") -> dict[str, Any]:
        """Approve or reapprove one demand and rebuild planning exactly once.

        The approved record is persisted first, then the operational requirements are
        synchronized to that approved version, then the selected planning engine is
        run once. A repository-specific batch context may collapse all physical saves
        into one write transaction.
        """
        with self._context("approve demand"):
            self._approve_record(self._repository, number, comment)
            self._sync_approved_demand(self._repository, number)
            summary = self._rebuild_planning(self._repository)
        return dict(summary)

    def request_correction(self, number: str, comment: str) -> None:
        """Return a submitted demand for correction with a mandatory reason."""
        reason = str(comment or "").strip()
        if not reason:
            raise ValueError("Un commentaire de correction est requis.")
        with self._context("request demand correction"):
            self._request_correction_record(self._repository, number, reason)

    def cancel(self, number: str) -> None:
        """Cancel a demand using the current V1 lifecycle semantics.

        Cancellation intentionally does not add a planning rebuild here. This tranche
        preserves the existing V1 behavior; any future policy for cancelling already
        approved operational requirements must be decided explicitly rather than
        introduced as an architecture side effect.
        """
        with self._context("cancel demand"):
            self._cancel_record(self._repository, number)
