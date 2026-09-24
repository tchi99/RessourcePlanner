from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from typing import Sequence

from .demand_cancellation import DemandCancellationPolicyReadModel
from .demand_workflow_policy import (
    ACTION_MODIFY,
    DemandWorkflowActionReadModel,
    demand_workflow_state,
)
from .errors import ApplicationNotFoundError
from .operational_contacts import (
    OperationalContactService,
    RequestLineContactResolution,
)
from .plan_delta import DemandApprovalStateReadModel
from .query_models import AssetRequirementReadModel, DemandMaterializedRequirementReadModel
from .query_ports import PlannerQueryPort
from .read_models import DemandLineReadModel, DemandPeriodReadModel, DemandReadModel


_EDITABLE_CANDIDATE_FIELDS = (
    "project_number",
    "requester_user_id",
    "priority",
    "description",
    "lines",
)


@dataclass(frozen=True, slots=True)
class DemandDetailAlternativeGroupReadModel:
    line_id: str
    group_key: str
    period_ids: tuple[str, ...]
    selected_period_id: str | None = None


@dataclass(frozen=True, slots=True)
class DemandDetailLineReadModel:
    line: DemandLineReadModel
    periods: tuple[DemandPeriodReadModel, ...] = ()
    alternative_groups: tuple[DemandDetailAlternativeGroupReadModel, ...] = ()
    contacts: RequestLineContactResolution | None = None


@dataclass(frozen=True, slots=True)
class DemandMaterializedPlanSummaryReadModel:
    requirement_count: int
    planned_hours: float
    covered_hours: float
    locked_hours: float
    requirements: tuple[DemandMaterializedRequirementReadModel, ...] = ()
    asset_requirement_count: int = 0
    asset_assigned_count: int = 0
    asset_usage_hours: float = 0.0
    asset_unbudgeted_requirement_count: int = 0
    asset_requirements: tuple[AssetRequirementReadModel, ...] = ()


@dataclass(frozen=True, slots=True)
class DemandDetailWorkflowReadModel:
    demand_number: str
    status: str
    version: int
    available_actions: tuple[str, ...]
    actions: tuple[DemandWorkflowActionReadModel, ...]
    cancellation: DemandCancellationPolicyReadModel | None = None


@dataclass(frozen=True, slots=True)
class DemandDetailPolicyReadModel:
    can_modify_candidate: bool
    can_edit_periods: bool
    can_change_operational_choices: bool
    editable_candidate_fields: tuple[str, ...]
    expected_request_version: int
    expected_operational_version: int | None
    envelope_decision: str | None
    reapproval_required: bool


@dataclass(frozen=True, slots=True)
class DemandDetailReadModel:
    demand: DemandReadModel
    version: int
    lines: tuple[DemandDetailLineReadModel, ...]
    periods: tuple[DemandPeriodReadModel, ...]
    materialized_plan: DemandMaterializedPlanSummaryReadModel
    workflow: DemandDetailWorkflowReadModel
    approval_state: DemandApprovalStateReadModel | None
    policy: DemandDetailPolicyReadModel
    diagnostics: tuple[str, ...] = ()


class DemandDetailService:
    """Compose the canonical demand-detail read model without persisting a new aggregate."""

    def __init__(
        self,
        queries: PlannerQueryPort,
        contacts: OperationalContactService,
    ) -> None:
        self._queries = queries
        self._contacts = contacts

    @staticmethod
    def _alternative_groups(
        line_id: str,
        periods: Sequence[DemandPeriodReadModel],
        diagnostics: list[str],
    ) -> tuple[DemandDetailAlternativeGroupReadModel, ...]:
        grouped: dict[str, list[DemandPeriodReadModel]] = defaultdict(list)
        for period in periods:
            group_key = str(period.alternative_group or "").strip()
            if period.kind == "ALTERNATIVE" and group_key:
                grouped[group_key].append(period)

        result: list[DemandDetailAlternativeGroupReadModel] = []
        for group_key in sorted(grouped):
            options = sorted(
                grouped[group_key],
                key=lambda row: (row.sequence, row.period_id),
            )
            selected = tuple(row.period_id for row in options if row.selected)
            if len(selected) > 1:
                diagnostics.append(
                    f"ALTERNATIVE_GROUP_MULTIPLE_SELECTIONS:{line_id}:{group_key}"
                )
            result.append(
                DemandDetailAlternativeGroupReadModel(
                    line_id=line_id,
                    group_key=group_key,
                    period_ids=tuple(row.period_id for row in options),
                    selected_period_id=selected[0] if selected else None,
                )
            )
        return tuple(result)

    def get(
        self,
        number: str,
        *,
        permissions: Sequence[str],
    ) -> DemandDetailReadModel:
        combined_reader = getattr(
            self._queries,
            "get_demand_with_cancellation_materialization",
            None,
        )
        combined = combined_reader(number) if callable(combined_reader) else None
        if combined is not None:
            demand, cancellation_materialization = combined
        else:
            demand = self._queries.get_demand(number)
            cancellation_materialization = None
        if demand is None:
            raise ApplicationNotFoundError(
                f"Demande {number} introuvable",
                code="demand_not_found",
                context={"demand_number": number},
            )

        periods = tuple(self._queries.list_demand_periods(demand.number))
        active_lines = tuple(row for row in demand.lines if row.active)
        contacts = self._contacts.resolve_request_lines(
            tuple(row.line_id for row in active_lines)
        )
        contacts_by_line = {row.line_id: row for row in contacts}
        periods_by_line: dict[str, list[DemandPeriodReadModel]] = defaultdict(list)
        diagnostics: list[str] = []
        active_line_ids = {row.line_id for row in active_lines}

        for period in periods:
            line_id = str(period.request_line_id or "").strip()
            if line_id:
                periods_by_line[line_id].append(period)
                if line_id not in active_line_ids:
                    diagnostics.append(
                        f"PERIOD_ACTIVE_LINE_NOT_IN_CANDIDATE:{line_id}:{period.period_id}"
                    )
            else:
                diagnostics.append(f"PERIOD_WITHOUT_LINE_ID:{period.period_id}")

        detail_lines: list[DemandDetailLineReadModel] = []
        for line in active_lines:
            line_periods = tuple(
                sorted(
                    periods_by_line.get(line.line_id, ()),
                    key=lambda row: (row.sequence, row.period_id),
                )
            )
            contact = contacts_by_line.get(line.line_id)
            if contact is None:
                diagnostics.append(f"CONTACT_CONTEXT_MISSING:{line.line_id}")
            else:
                diagnostics.extend(
                    f"CONTACT:{line.line_id}:{code}"
                    for code in contact.diagnostics
                )
                diagnostics.extend(
                    f"CONTACT:{line.line_id}:RESPONSIBLE:{code}"
                    for code in contact.operational_responsible.diagnostics
                )
                diagnostics.extend(
                    f"CONTACT:{line.line_id}:COORDINATOR:{code}"
                    for code in contact.coordinator.diagnostics
                )
            detail_lines.append(
                DemandDetailLineReadModel(
                    line=line,
                    periods=line_periods,
                    alternative_groups=self._alternative_groups(
                        line.line_id,
                        line_periods,
                        diagnostics,
                    ),
                    contacts=contact,
                )
            )

        approval_state = self._queries.demand_approval_state(demand.number)
        if approval_state is None:
            diagnostics.append("APPROVAL_STATE_UNAVAILABLE")
        else:
            diagnostics.extend(approval_state.diagnostics)

        requirements = tuple(self._queries.list_demand_requirements(demand.number))
        asset_requirements = tuple(
            self._queries.list_demand_asset_requirements(demand.number)
        )
        materialized_plan = DemandMaterializedPlanSummaryReadModel(
            requirement_count=len(requirements),
            planned_hours=round(sum(row.planned_hours for row in requirements), 2),
            covered_hours=round(sum(row.covered_hours for row in requirements), 2),
            locked_hours=round(sum(row.locked_hours for row in requirements), 2),
            requirements=requirements,
            asset_requirement_count=len(asset_requirements),
            asset_assigned_count=sum(
                1 for row in asset_requirements if row.asset_id is not None
            ),
            asset_usage_hours=round(
                sum(
                    row.usage_hours
                    for row in asset_requirements
                    if row.usage_hours is not None
                ),
                2,
            ),
            asset_unbudgeted_requirement_count=sum(
                1 for row in asset_requirements if row.usage_hours is None
            ),
            asset_requirements=asset_requirements,
        )

        workflow_state = demand_workflow_state(
            demand,
            permissions=permissions,
            materialization=cancellation_materialization,
        )
        workflow = DemandDetailWorkflowReadModel(
            demand_number=workflow_state.demand_number,
            status=workflow_state.status,
            version=workflow_state.version,
            available_actions=workflow_state.available_actions,
            actions=workflow_state.actions,
            cancellation=workflow_state.cancellation,
        )
        can_modify = ACTION_MODIFY in workflow.available_actions
        operational_version = (
            approval_state.operational_version
            if approval_state is not None
            else None
        )
        envelope_decision = (
            approval_state.envelope_decision
            if approval_state is not None
            else None
        )
        policy = DemandDetailPolicyReadModel(
            can_modify_candidate=can_modify,
            can_edit_periods=can_modify,
            can_change_operational_choices=(
                can_modify
                and approval_state is not None
                and approval_state.active_revision_id is not None
            ),
            editable_candidate_fields=(
                _EDITABLE_CANDIDATE_FIELDS if can_modify else ()
            ),
            expected_request_version=int(demand.version),
            expected_operational_version=operational_version,
            envelope_decision=envelope_decision,
            reapproval_required=envelope_decision == "REAPPROVAL_REQUIRED",
        )

        decorated_demand = replace(
            demand,
            cancellation_policy=(
                workflow_state.cancellation.to_dict()
                if workflow_state.cancellation is not None
                else None
            ),
        )
        return DemandDetailReadModel(
            demand=decorated_demand,
            version=int(demand.version),
            lines=tuple(detail_lines),
            periods=periods,
            materialized_plan=materialized_plan,
            workflow=workflow,
            approval_state=approval_state,
            policy=policy,
            diagnostics=tuple(dict.fromkeys(value for value in diagnostics if value)),
        )
