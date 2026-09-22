from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import nullcontext
from datetime import date, datetime
from typing import Any, ContextManager

from ..domain.demand_periods import DemandPeriodDefinition, validate_period_definitions
from ..domain.request_lines import default_legacy_hours
from .command_ports import ApprovedDemandSyncPort, PlanningCommandPort
from .commands import (
    DemandAlternativeSelectCommand,
    DemandOperationalConfirmationCommand,
    DemandApproveCommand,
    DemandCancelCommand,
    DemandCorrectionCommand,
    DemandCreateCommand,
    DemandPeriodsReplaceCommand,
    DemandSubmitCommand,
    DemandUpdateCommand,
)
from .errors import (
    ApplicationConflictError,
    ApplicationNotFoundError,
    ApplicationOperationError,
    ApplicationValidationError,
    call_application_port,
)
from .demand_workflow_policy import (
    ACTION_APPROVE,
    ACTION_CANCEL,
    ACTION_CORRECTION,
    ACTION_MODIFY,
    ACTION_SUBMIT,
    DemandWorkflowBlock,
    DemandWorkflowReadModel,
    assert_demand_action,
    demand_workflow_state,
)
from .security import PERMISSION_APPROVE_DEMANDS, PERMISSION_MANAGE_DEMANDS
from .read_models import DemandOperationalChoiceReadModel, DemandPeriodReadModel
from .repository_ports import (
    DemandOperationalChoiceRepositoryPort,
    DemandPeriodRepositoryPort,
    DemandRepositoryPort,
)


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
        "RequestLines",
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
        operational_choices: DemandOperationalChoiceRepositoryPort | None = None,
        current_user: str = "",
        permissions: Sequence[str] | None = None,
        batch: Callable[[str], ContextManager[Any]] | None = None,
    ) -> None:
        self._demands = demands
        self._planning = planning
        self._approved_sync = approved_sync
        self._periods = periods
        self._operational_choices = operational_choices
        self._current_user = str(current_user or "")
        self._permissions = tuple(permissions) if permissions is not None else (
            PERMISSION_MANAGE_DEMANDS,
            PERMISSION_APPROVE_DEMANDS,
        )
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

    def _operational_choice_repository(
        self,
    ) -> DemandOperationalChoiceRepositoryPort:
        if self._operational_choices is None:
            raise ApplicationOperationError(
                "Les choix opérationnels versionnés ne sont pas disponibles dans ce runtime.",
                code="operational_choices_unavailable",
            )
        return self._operational_choices

    def operational_choice_state(
        self,
        number: str,
    ) -> DemandOperationalChoiceReadModel | None:
        identifier = self._required_identifier(number, entity="demand")
        return call_application_port(
            lambda: self._operational_choice_repository().state_for_demand(
                identifier
            ),
            code_prefix="operational_choice_lookup",
            context={"demand_number": identifier},
        )

    @staticmethod
    def _period_line_scope(existing: Any, request_line_id: str | None) -> str | None:
        if bool(existing.line_mode):
            wanted = str(request_line_id or "").strip()
            if not wanted:
                raise ApplicationConflictError(
                    "Les périodes d'une demande multi-lignes doivent cibler une ligne.",
                    code="demand_line_period_scope_required",
                    context={"demand_number": existing.number},
                )
            line = next(
                (
                    row
                    for row in existing.lines
                    if row.active and str(row.line_id) == wanted
                ),
                None,
            )
            if line is None:
                raise ApplicationNotFoundError(
                    f"Ligne {wanted} introuvable pour la demande {existing.number}.",
                    code="demand_line_not_found",
                    context={
                        "demand_number": existing.number,
                        "request_line_id": wanted,
                    },
                )
            if line.kind != "WORKFORCE":
                raise ApplicationValidationError(
                    "Seules les lignes WORKFORCE supportent les périodes dans #288D.",
                    code="demand_line_kind_unsupported",
                    context={"line_id": line.line_id, "kind": line.kind},
                )
            return wanted

        if request_line_id is not None:
            raise ApplicationConflictError(
                "Les demandes historiques à une ligne utilisent les endpoints de périodes de la demande.",
                code="demand_legacy_period_scope_invalid",
                context={"demand_number": existing.number},
            )
        return None

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

    def _workflow_business_blocks(
        self,
        existing: Any,
    ) -> Mapping[str, DemandWorkflowBlock]:
        return {}

    def workflow_state(self, number: str) -> DemandWorkflowReadModel:
        identifier = self._required_identifier(number, entity="demand")
        existing = self._demand_or_not_found(identifier)
        return demand_workflow_state(
            existing,
            permissions=self._permissions,
            business_blocks=self._workflow_business_blocks(existing),
        )

    @staticmethod
    def _assert_expected_version(existing: Any, expected_version: int | None) -> None:
        if expected_version is None:
            return
        if int(expected_version) != int(existing.version):
            raise ApplicationConflictError(
                "La demande a été modifiée depuis sa lecture.",
                code="demand_version_conflict",
                context={
                    "demand_number": existing.number,
                    "expected_version": int(expected_version),
                    "current_version": int(existing.version),
                },
            )

    def _assert_workflow_action(
        self,
        existing: Any,
        action: str,
        *,
        expected_version: int | None = None,
    ) -> None:
        self._assert_expected_version(existing, expected_version)
        assert_demand_action(
            existing,
            action,
            permissions=self._permissions,
            business_blocks=self._workflow_business_blocks(existing),
        )

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
        expected_version = data.pop("ExpectedVersion", None)
        self._assert_workflow_action(
            existing,
            ACTION_MODIFY,
            expected_version=expected_version,
        )
        if "RequestLines" in data:
            if expected_version is None:
                raise ApplicationValidationError(
                    "expected_version est requis pour modifier les lignes d'une demande.",
                    code="demand_version_required",
                    context={"demand_number": number},
                )
            data["ExpectedVersion"] = int(expected_version)
        if "RequestLines" not in data and not existing.line_mode:
            final_count = int(data.get("NombreRessources", existing.resource_count) or 1)
            final_hours = data.get("TempsEstimeHeures", existing.estimated_hours)
            if final_hours is not None:
                numeric_hours = float(final_hours)
                if numeric_hours <= 0:
                    raise ApplicationValidationError(
                        "Les heures doivent être supérieures à zéro lorsqu'elles sont renseignées.",
                        code="demand_estimated_hours_invalid",
                        context={"estimated_hours": numeric_hours},
                    )
                if numeric_hours < final_count * 0.01:
                    raise ApplicationValidationError(
                        "Les heures totales sont insuffisantes pour produire un besoin positif par ressource.",
                        code="demand_hours_split_invalid",
                        context={
                            "estimated_hours": numeric_hours,
                            "resource_count": final_count,
                        },
                    )
        if "NumeroProjet" in data and not str(data["NumeroProjet"] or "").strip():
            raise ApplicationValidationError(
                "Le projet est requis.",
                code="demand_project_required",
                context={"field": "project_number"},
            )
        if "RequestLines" not in data and not existing.line_mode:
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
        self._assert_workflow_action(existing, ACTION_MODIFY)
        request_line_id = self._period_line_scope(
            existing,
            command.request_line_id,
        )
        periods = self._period_repository()

        try:
            definitions = tuple(item.to_definition() for item in command.periods)
            validate_period_definitions(definitions)
        except ValueError as exc:
            raise ApplicationValidationError(
                str(exc),
                code="demand_periods_invalid",
                context={
                    "demand_number": number,
                    "request_line_id": request_line_id,
                },
            ) from exc

        if request_line_id is not None and any(
            int(row.resource_count) != 1 for row in definitions
        ):
            raise ApplicationValidationError(
                "Une période rattachée à une RequestLine représente exactement un slot.",
                code="demand_line_period_resource_count_invalid",
                context={
                    "demand_number": number,
                    "request_line_id": request_line_id,
                },
            )

        current = call_application_port(
            lambda: (
                periods.list_for_demand(number)
                if request_line_id is None
                else periods.list_for_demand(
                    number,
                    request_line_id=request_line_id,
                )
            ),
            code_prefix="demand_periods_lookup",
            context={
                "demand_number": number,
                "request_line_id": request_line_id,
            },
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
        comment = (
            f"Périodes détaillées de la ligne {request_line_id} modifiées"
            if request_line_id is not None
            else "Périodes détaillées de la demande modifiées"
        )
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
                lambda: (
                    periods.replace_for_demand(number, definitions)
                    if request_line_id is None
                    else periods.replace_for_demand(
                        number,
                        definitions,
                        request_line_id=request_line_id,
                    )
                ),
                code_prefix="demand_periods_replace",
                context={
                    "demand_number": number,
                    "request_line_id": request_line_id,
                },
            )
            call_application_port(
                lambda: self._demands.update(
                    number,
                    status_update,
                    action="Modification périodes",
                    comment=comment,
                ),
                code_prefix="demand_periods_audit",
                context={
                    "demand_number": number,
                    "request_line_id": request_line_id,
                },
            )
        return tuple(updated), reapproval_required

    def select_alternative_command(
        self,
        command: DemandAlternativeSelectCommand,
    ) -> Mapping[str, Any] | None:
        number = self._required_identifier(command.number, entity="demand")
        group = self._required_identifier(
            command.alternative_group,
            entity="alternative_group",
        )
        period_id = self._required_identifier(command.period_id, entity="period")
        existing = self._demand_or_not_found(number)
        self._assert_workflow_action(existing, ACTION_MODIFY)
        request_line_id = self._period_line_scope(
            existing,
            command.request_line_id,
        )

        use_operational = bool(command.operational) or (
            existing.status == "En planification"
            and self._operational_choices is not None
            and self.operational_choice_state(number) is not None
        )
        if use_operational:
            with self._context("select operational alternative"):
                call_application_port(
                    lambda: self._operational_choice_repository().select_alternative(
                        number,
                        group,
                        period_id,
                        request_line_id=request_line_id,
                        expected_version=command.expected_operational_version,
                    ),
                    code_prefix="operational_alternative_select",
                    context={
                        "demand_number": number,
                        "request_line_id": request_line_id,
                        "alternative_group": group,
                        "period_id": period_id,
                    },
                )
                sync_operational = getattr(
                    self._approved_sync,
                    "sync_operational_choices",
                    None,
                )
                if not callable(sync_operational):
                    raise ApplicationOperationError(
                        "La synchronisation des choix opérationnels n'est pas disponible.",
                        code="operational_choice_sync_unavailable",
                    )
                call_application_port(
                    lambda: sync_operational(number),
                    code_prefix="operational_choice_sync",
                    context={
                        "demand_number": number,
                        "alternative_group": group,
                    },
                )
                summary = call_application_port(
                    self._planning.rebuild,
                    code_prefix="operational_choice_rebuild",
                    context={
                        "demand_number": number,
                        "alternative_group": group,
                    },
                )
            return dict(summary)

        periods = self._period_repository()
        selections = call_application_port(
            lambda: (
                periods.selections_for_demand(number)
                if request_line_id is None
                else periods.selections_for_demand(
                    number,
                    request_line_id=request_line_id,
                )
            ),
            code_prefix="demand_period_selection_lookup",
            context={
                "demand_number": number,
                "request_line_id": request_line_id,
                "alternative_group": group,
            },
        )
        if str(selections.get(group) or "").strip() == period_id:
            return None

        with self._context("select demand alternative"):
            call_application_port(
                lambda: (
                    periods.select_alternative(number, group, period_id)
                    if request_line_id is None
                    else periods.select_alternative(
                        number,
                        group,
                        period_id,
                        request_line_id=request_line_id,
                    )
                ),
                code_prefix="demand_period_select",
                context={
                    "demand_number": number,
                    "request_line_id": request_line_id,
                    "alternative_group": group,
                    "period_id": period_id,
                },
            )
        return None

    def set_operational_confirmation_command(
        self,
        command: DemandOperationalConfirmationCommand,
    ) -> Mapping[str, Any]:
        number = self._required_identifier(command.number, entity="demand")
        existing = self._demand_or_not_found(number)
        self._assert_workflow_action(existing, ACTION_MODIFY)
        request_line_id = self._period_line_scope(
            existing,
            command.request_line_id,
        )
        with self._context("set operational confirmation"):
            call_application_port(
                lambda: self._operational_choice_repository().set_confirmation(
                    number,
                    command.confirmation,
                    request_line_id=request_line_id,
                    period_id=command.period_id,
                    expected_version=command.expected_operational_version,
                ),
                code_prefix="operational_confirmation",
                context={
                    "demand_number": number,
                    "request_line_id": request_line_id,
                    "period_id": command.period_id,
                },
            )
            sync_operational = getattr(
                self._approved_sync,
                "sync_operational_choices",
                None,
            )
            if not callable(sync_operational):
                raise ApplicationOperationError(
                    "La synchronisation des choix opérationnels n'est pas disponible.",
                    code="operational_choice_sync_unavailable",
                )
            call_application_port(
                lambda: sync_operational(number),
                code_prefix="operational_confirmation_sync",
                context={"demand_number": number},
            )
            summary = call_application_port(
                self._planning.rebuild,
                code_prefix="operational_confirmation_rebuild",
                context={"demand_number": number},
            )
        return dict(summary)

    def submit_command(self, command: DemandSubmitCommand) -> None:
        number = self._required_identifier(command.number, entity="demand")
        existing = self._demand_or_not_found(number)
        self._assert_workflow_action(
            existing,
            ACTION_SUBMIT,
            expected_version=command.expected_version,
        )
        active_lines = (
            tuple(line for line in existing.lines if line.active)
            if existing.line_mode
            else ()
        )
        if active_lines:
            for line in active_lines:
                if line.kind != "WORKFORCE":
                    raise ApplicationValidationError(
                        "Seules les lignes WORKFORCE peuvent être soumises dans cette tranche.",
                        code="demand_line_kind_unsupported",
                        context={"line_id": line.line_id, "kind": line.kind},
                    )
                if line.desired_start is None:
                    raise ApplicationValidationError(
                        "Chaque ligne doit avoir une date de début avant soumission.",
                        code="demand_line_start_required",
                        context={"line_id": line.line_id},
                    )
                if line.estimated_hours is None or line.estimated_hours <= 0:
                    raise ApplicationValidationError(
                        "Chaque ligne doit avoir un effort résolu avant soumission.",
                        code="demand_line_effort_required",
                        context={"line_id": line.line_id},
                    )
        submit_updates: dict[str, Any] = {"Statut": "Soumise"}
        has_period_effort = False
        if (
            existing is not None
            and not existing.line_mode
            and existing.estimated_hours is None
            and existing.estimated_days is None
            and self._periods is not None
        ):
            period_rows = call_application_port(
                lambda: self._periods.list_for_demand(number),
                code_prefix="demand_submit_periods",
                context={"demand_number": number},
            )
            has_period_effort = bool(period_rows)
        if (
            existing is not None
            and not existing.line_mode
            and existing.estimated_hours is None
            and existing.estimated_days is None
            and not has_period_effort
        ):
            raise ApplicationValidationError(
                "Une demande soumise doit préciser des heures, un nombre de jours ou des périodes détaillées.",
                code="demand_effort_required",
                context={"demand_number": number},
            )
        if (
            existing is not None
            and not existing.line_mode
            and existing.estimated_hours is None
            and existing.estimated_days is not None
        ):
            submit_updates["TempsEstimeHeures"] = default_legacy_hours(
                estimated_hours=None,
                estimated_days=existing.estimated_days,
                resource_count=existing.resource_count,
            )
            submit_updates["RequestLineHoursSource"] = "DEFAULT_8H"
        with self._context("submit demand"):
            call_application_port(
                lambda: self._demands.update(
                    number,
                    submit_updates,
                    action="Soumission",
                    comment="Demande soumise pour approbation",
                ),
                code_prefix="demand_submit",
                context={"demand_number": number},
            )

    def approve_command(self, command: DemandApproveCommand) -> dict[str, Any]:
        number = self._required_identifier(command.number, entity="demand")
        existing = self._demand_or_not_found(number)
        self._assert_workflow_action(
            existing,
            ACTION_APPROVE,
            expected_version=command.expected_version,
        )
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
        existing = self._demand_or_not_found(number)
        self._assert_workflow_action(
            existing,
            ACTION_CORRECTION,
            expected_version=command.expected_version,
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
        existing = self._demand_or_not_found(number)
        self._assert_workflow_action(
            existing,
            ACTION_CANCEL,
            expected_version=command.expected_version,
        )
        cancel_materialized = getattr(self._approved_sync, "cancel_materialized", None)
        with self._context("cancel demand"):
            if callable(cancel_materialized):
                call_application_port(
                    lambda: cancel_materialized(number),
                    code_prefix="demand_cancel_materialized",
                    context={"demand_number": number},
                )
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
            if callable(cancel_materialized):
                call_application_port(
                    self._planning.rebuild,
                    code_prefix="demand_cancel_rebuild",
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
