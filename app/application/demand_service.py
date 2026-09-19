from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import nullcontext
from datetime import date, datetime
from typing import Any, ContextManager

from ..domain.demand_periods import DemandPeriodDefinition, validate_period_definitions
from .command_ports import ApprovedDemandSyncPort, PlanningCommandPort
from .commands import (
    DemandAlternativeSelectCommand,
    DemandApproveCommand,
    DemandCancelCommand,
    DemandCorrectionCommand,
    DemandCreateCommand,
    DemandPeriodsReplaceCommand,
    DemandSubmitCommand,
    DemandUpdateCommand,
)
from .errors import (
    ApplicationNotFoundError,
    ApplicationOperationError,
    ApplicationValidationError,
    call_application_port,
)
from .read_models import DemandPeriodReadModel
from .repository_ports import DemandPeriodRepositoryPort, DemandRepositoryPort


BUSINESS_DEMAND_FIELDS = frozenset(
    {
        "NumeroProjet",
        "NomProjet",
        "Client",
        "ChargeProjet",
        "SourceEffortID",
        "TaskCode",
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


class DemandService:
    """Application service for the workforce-demand lifecycle."""

    def __init__(
        self,
        demands: DemandRepositoryPort,
        planning: PlanningCommandPort,
        approved_sync: ApprovedDemandSyncPort,
        *,
        periods: DemandPeriodRepositoryPort | None = None,
        current_user: str = "",
        batch: Callable[[str], ContextManager[Any]] | None = None,
    ) -> None:
        self._demands = demands
        self._planning = planning
        self._approved_sync = approved_sync
        self._periods = periods
        self._current_user = str(current_user or "")
        self._batch = batch

    def _context(self, label: str) -> ContextManager[Any]:
        return self._batch(label) if self._batch is not None else nullcontext()

    @staticmethod
    def _required_identifier(value: object, *, entity: str) -> str:
        identifier = str(value or "").strip()
        if not identifier:
            raise ApplicationValidationError(
                f"L'identifiant de {entity} est requis.",
                code=f"{entity}_id_required",
            )
        return identifier

    @staticmethod
    def _validate_window(start: date | None, end: date | None) -> None:
        if start is None:
            raise ApplicationValidationError(
                "La date de début est requise.",
                code="demand_start_required",
                context={"field": "desired_start"},
            )
        if end is not None and end < start:
            raise ApplicationValidationError(
                "La date de fin ne peut pas précéder la date de début.",
                code="demand_date_window_invalid",
                context={"start": start.isoformat(), "end": end.isoformat()},
            )

    def _period_repository(self) -> DemandPeriodRepositoryPort:
        if self._periods is None:
            raise ApplicationOperationError(
                "La gestion détaillée des périodes n'est pas disponible dans ce runtime.",
                code="demand_periods_unavailable",
            )
        return self._periods

    @staticmethod
    def _period_signature_from_definition(period: DemandPeriodDefinition) -> tuple[Any, ...]:
        return (
            period.period_id,
            period.start_date,
            period.end_date,
            float(period.hours),
            period.kind,
            period.alternative_group,
            period.confirmation,
            period.proposed_resource,
            int(period.resource_count),
            period.desired_active_days,
            period.note,
        )

    @staticmethod
    def _period_signature_from_read_model(period: DemandPeriodReadModel) -> tuple[Any, ...]:
        return (
            period.period_id,
            period.start_date,
            period.end_date,
            float(period.hours),
            period.kind,
            period.alternative_group,
            period.confirmation,
            period.proposed_resource,
            int(period.resource_count),
            period.desired_active_days,
            period.note or "",
        )

    def _demand_or_not_found(self, number: str):
        existing = call_application_port(
            lambda: self._demands.get(number),
            code_prefix="demand_lookup",
            context={"demand_number": number},
        )
        if existing is None:
            raise ApplicationNotFoundError(
                f"Demande {number} introuvable",
                code="demand_not_found",
                context={"demand_number": number},
            )
        return existing

    def create_command(self, command: DemandCreateCommand) -> str:
        values = command.to_repository_values()
        with self._context("create demand"):
            number = call_application_port(
                lambda: self._demands.create(values, submit=bool(command.submit)),
                code_prefix="demand_create",
                context={"project_number": command.project_number},
            )

        normalized = str(number or "").strip()
        if not normalized:
            raise ApplicationOperationError(
                "La création de la demande n'a retourné aucun numéro.",
                code="demand_create_id_missing",
                context={"project_number": command.project_number},
            )
        return normalized

    def modify_command(self, command: DemandUpdateCommand) -> bool:
        number = self._required_identifier(command.number, entity="demand")
        existing = self._demand_or_not_found(number)

        data = command.to_repository_values()
        if "NumeroProjet" in data and not str(data["NumeroProjet"] or "").strip():
            raise ApplicationValidationError(
                "Le projet est requis.",
                code="demand_project_required",
                context={"field": "project_number"},
            )
        start = data.get("DateDebutSouhaitee", existing.desired_start)
        end = data.get("DateFinSouhaitee", existing.desired_end)
        self._validate_window(
            start if isinstance(start, date) else None,
            end if isinstance(end, date) else None,
        )

        reapproval_required = (
            existing.status == "En planification"
            and bool(BUSINESS_DEMAND_FIELDS.intersection(data))
        )

        audit_comment = str(command.comment or "").strip()
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
            call_application_port(
                lambda: self._demands.update(
                    number,
                    data,
                    action="Modification",
                    comment=audit_comment,
                ),
                code_prefix="demand_update",
                context={"demand_number": number},
            )
        return reapproval_required

    def replace_periods_command(
        self,
        command: DemandPeriodsReplaceCommand,
    ) -> tuple[Sequence[DemandPeriodReadModel], bool]:
        number = self._required_identifier(command.number, entity="demand")
        existing = self._demand_or_not_found(number)
        periods = self._period_repository()

        try:
            definitions = tuple(item.to_definition() for item in command.periods)
            validate_period_definitions(definitions)
        except ValueError as exc:
            raise ApplicationValidationError(
                str(exc),
                code="demand_periods_invalid",
                context={"demand_number": number},
            ) from exc

        current = call_application_port(
            lambda: periods.list_for_demand(number),
            code_prefix="demand_periods_lookup",
            context={"demand_number": number},
        )
        old_signature = tuple(
            self._period_signature_from_read_model(row) for row in current
        )
        new_signature = tuple(
            self._period_signature_from_definition(row) for row in definitions
        )
        if old_signature == new_signature:
            return tuple(current), False

        reapproval_required = existing.status == "En planification"
        status_update: dict[str, Any] = {}
        comment = "Périodes détaillées de la demande modifiées"
        if reapproval_required:
            status_update = {
                "Statut": "Soumise",
                "ApprouvePar": None,
                "DateApprobation": None,
                "CommentaireApprobation": (
                    "Enveloppe de périodes modifiée après approbation — nouvelle approbation requise"
                ),
            }
            comment += "; nouvelle approbation requise et planification existante conservée"

        with self._context("replace demand periods"):
            updated = call_application_port(
                lambda: periods.replace_for_demand(number, definitions),
                code_prefix="demand_periods_replace",
                context={"demand_number": number},
            )
            call_application_port(
                lambda: self._demands.update(
                    number,
                    status_update,
                    action="Modification périodes",
                    comment=comment,
                ),
                code_prefix="demand_periods_audit",
                context={"demand_number": number},
            )
        return tuple(updated), reapproval_required

    def select_alternative_command(
        self,
        command: DemandAlternativeSelectCommand,
    ) -> Mapping[str, Any] | None:
        number = self._required_identifier(command.number, entity="demand")
        group = self._required_identifier(command.alternative_group, entity="alternative_group")
        period_id = self._required_identifier(command.period_id, entity="period")
        existing = self._demand_or_not_found(number)
        periods = self._period_repository()

        selections = call_application_port(
            lambda: periods.selections_for_demand(number),
            code_prefix="demand_period_selection_lookup",
            context={"demand_number": number, "alternative_group": group},
        )
        if str(selections.get(group) or "").strip() == period_id:
            return None

        with self._context("select demand alternative"):
            call_application_port(
                lambda: periods.select_alternative(number, group, period_id),
                code_prefix="demand_period_select",
                context={
                    "demand_number": number,
                    "alternative_group": group,
                    "period_id": period_id,
                },
            )
            if existing.status != "En planification":
                return None
            call_application_port(
                lambda: self._approved_sync.sync_approved(number),
                code_prefix="demand_period_selection_sync",
                context={"demand_number": number, "alternative_group": group},
            )
            summary = call_application_port(
                self._planning.rebuild,
                code_prefix="demand_period_selection_rebuild",
                context={"demand_number": number, "alternative_group": group},
            )
        return dict(summary)

    def submit_command(self, command: DemandSubmitCommand) -> None:
        number = self._required_identifier(command.number, entity="demand")
        with self._context("submit demand"):
            call_application_port(
                lambda: self._demands.update(
                    number,
                    {"Statut": "Soumise"},
                    action="Soumission",
                    comment="Demande soumise pour approbation",
                ),
                code_prefix="demand_submit",
                context={"demand_number": number},
            )

    def approve_command(self, command: DemandApproveCommand) -> dict[str, Any]:
        number = self._required_identifier(command.number, entity="demand")
        comment = str(command.comment or "")
        with self._context("approve demand"):
            call_application_port(
                lambda: self._demands.update(
                    number,
                    {
                        "Statut": "En planification",
                        "ApprouvePar": self._current_user,
                        "DateApprobation": datetime.now(),
                        "CommentaireApprobation": comment,
                    },
                    action="Approbation",
                    comment=comment or "Demande approuvée",
                ),
                code_prefix="demand_approve",
                context={"demand_number": number},
            )
            call_application_port(
                lambda: self._approved_sync.sync_approved(number),
                code_prefix="demand_approval_sync",
                context={"demand_number": number},
            )
            summary = call_application_port(
                self._planning.rebuild,
                code_prefix="demand_approval_rebuild",
                context={"demand_number": number},
            )
        return dict(summary)

    def request_correction_command(self, command: DemandCorrectionCommand) -> None:
        number = self._required_identifier(command.number, entity="demand")
        reason = str(command.comment or "").strip()
        if not reason:
            raise ApplicationValidationError(
                "Un commentaire de correction est requis.",
                code="demand_correction_comment_required",
                context={"demand_number": number},
            )
        with self._context("request demand correction"):
            call_application_port(
                lambda: self._demands.update(
                    number,
                    {
                        "Statut": "À corriger",
                        "CommentaireApprobation": reason,
                    },
                    action="Retour pour correction",
                    comment=reason,
                ),
                code_prefix="demand_correction",
                context={"demand_number": number},
            )

    def cancel_command(self, command: DemandCancelCommand) -> None:
        number = self._required_identifier(command.number, entity="demand")
        with self._context("cancel demand"):
            call_application_port(
                lambda: self._demands.update(
                    number,
                    {"Statut": "Annulée"},
                    action="Annulation",
                    comment="Demande annulée",
                ),
                code_prefix="demand_cancel",
                context={"demand_number": number},
            )

    def create(self, data: Mapping[str, Any], *, submit: bool = False) -> str:
        """Compatibility adapter for current NiceGUI callers."""

        return self.create_command(DemandCreateCommand.from_mapping(data, submit=submit))

    def modify(
        self,
        number: str,
        updates: Mapping[str, Any],
        comment: str = "Demande modifiée dans l'application",
    ) -> bool:
        return self.modify_command(
            DemandUpdateCommand.from_mapping(number, updates, comment=comment)
        )

    def submit(self, number: str) -> None:
        self.submit_command(DemandSubmitCommand(number))

    def approve(self, number: str, comment: str = "") -> dict[str, Any]:
        return self.approve_command(DemandApproveCommand(number, comment))

    def request_correction(self, number: str, comment: str) -> None:
        self.request_correction_command(DemandCorrectionCommand(number, comment))

    def cancel(self, number: str) -> None:
        self.cancel_command(DemandCancelCommand(number))
