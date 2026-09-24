from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Mapping, Protocol, Sequence, cast

from .demand_service import DemandService
from .demand_workflow_policy import (
    ACTION_EMERGENCY_PLAN,
    DemandWorkflowBlock,
)
from .errors import (
    ApplicationConflictError,
    ApplicationOperationError,
    ApplicationValidationError,
    call_application_port,
)
from .facade import ApplicationFacade
from .read_models import DemandPeriodReadModel, DemandReadModel
from .results import DemandMutationResult, PlanningResult


@dataclass(frozen=True, slots=True)
class DemandEmergencyOverrideCommand:
    number: str
    comment: str
    expected_version: int | None = None


class EmergencyDemandRepositoryPort(Protocol):
    def activate_emergency_override(
        self,
        number: str,
        *,
        reason: str,
        actor_name: str,
        occurred_at: datetime,
        previous_status: str,
    ) -> None: ...

    def clear_emergency_override(self, number: str) -> None: ...


def current_week_window(today: date) -> tuple[date, date]:
    start = today - timedelta(days=today.weekday())
    return start, start + timedelta(days=6)


def _effective_periods(
    periods: Sequence[DemandPeriodReadModel],
) -> tuple[DemandPeriodReadModel, ...]:
    return tuple(
        row for row in periods if row.kind == "CUMULATIVE" or row.selected
    )


def _line_emergency_windows(
    demand: DemandReadModel,
    periods: Sequence[DemandPeriodReadModel],
) -> tuple[tuple[date, date], ...] | None:
    periods_by_line: dict[str, list[DemandPeriodReadModel]] = {}
    for period in periods:
        if period.request_line_id:
            periods_by_line.setdefault(period.request_line_id, []).append(period)

    windows: list[tuple[date, date]] = []
    for line in demand.lines:
        if not line.active:
            continue
        line_periods = periods_by_line.get(line.line_id, [])
        if line_periods:
            effective = _effective_periods(line_periods)
            if not effective:
                return None
            windows.extend((row.start_date, row.end_date) for row in effective)
            continue
        if line.desired_start is None:
            return None
        windows.append((line.desired_start, line.desired_end or line.desired_start))
    return tuple(windows) if windows else None


def emergency_window(
    demand: DemandReadModel,
    periods: Sequence[DemandPeriodReadModel] = (),
) -> tuple[date, date] | None:
    if demand.line_mode:
        windows = _line_emergency_windows(demand, periods)
        if not windows:
            return None
        return (
            min(start for start, _end in windows),
            max(end for _start, end in windows),
        )
    if periods:
        effective = _effective_periods(periods)
        if not effective:
            return None
        return (
            min(row.start_date for row in effective),
            max(row.end_date for row in effective),
        )
    if demand.desired_start is None:
        return None
    return demand.desired_start, demand.desired_end or demand.desired_start


def emergency_override_eligibility(
    demand: DemandReadModel,
    *,
    today: date,
    periods: Sequence[DemandPeriodReadModel] = (),
) -> tuple[bool, str | None]:
    if demand.emergency_override_active:
        return False, "ALREADY_ACTIVE"
    if str(demand.status or "").strip().casefold() != "soumise":
        return False, "STATUS_NOT_SUBMITTED"
    if str(demand.priority or "").strip().casefold() not in {"urgent", "urgente"}:
        return False, "NOT_URGENT"

    week_start, week_end = current_week_window(today)
    if demand.line_mode:
        windows = _line_emergency_windows(demand, periods)
        if not windows:
            return False, "WINDOW_INCOMPLETE"
        if not any(
            line_end >= week_start and line_start <= week_end
            for line_start, line_end in windows
        ):
            return False, "OUTSIDE_CURRENT_WEEK"
        return True, None

    if periods:
        effective = _effective_periods(periods)
        if not effective:
            return False, "WINDOW_INCOMPLETE"
        if not any(
            period.end_date >= week_start and period.start_date <= week_end
            for period in effective
        ):
            return False, "OUTSIDE_CURRENT_WEEK"
        return True, None

    window = emergency_window(demand)
    if window is None:
        return False, "WINDOW_INCOMPLETE"
    start, end = window
    if end < week_start or start > week_end:
        return False, "OUTSIDE_CURRENT_WEEK"
    return True, None


class EmergencyDemandService(DemandService):
    """Demand lifecycle extended with a one-shot, auditable emergency materialization."""

    def __init__(self, *args, today_provider: Callable[[], date] = date.today, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._today_provider = today_provider

    def _workflow_business_blocks(
        self,
        existing: DemandReadModel,
    ) -> Mapping[str, DemandWorkflowBlock]:
        blocks = dict(super()._workflow_business_blocks(existing))
        periods = self._emergency_periods(existing.number)
        eligible, reason = emergency_override_eligibility(
            existing,
            today=self._today_provider(),
            periods=periods,
        )
        if eligible:
            return blocks

        messages = {
            "ALREADY_ACTIVE": (
                "demand_emergency_override_already_active",
                "Une dérogation urgente est déjà active. La demande doit être régularisée par l'approbation normale avant toute nouvelle dérogation.",
                "conflict",
            ),
            "STATUS_NOT_SUBMITTED": (
                "demand_emergency_status_not_submitted",
                "La dérogation urgente est réservée aux demandes Soumises.",
                "validation",
            ),
            "NOT_URGENT": (
                "demand_emergency_not_urgent",
                "La demande doit être marquée Urgent pour utiliser cette dérogation.",
                "validation",
            ),
            "WINDOW_INCOMPLETE": (
                "demand_emergency_window_incomplete",
                "La fenêtre urgente ne peut pas être déterminée; sélectionner les alternatives requises ou compléter les dates.",
                "validation",
            ),
            "OUTSIDE_CURRENT_WEEK": (
                "demand_emergency_outside_current_week",
                "La dérogation urgente est limitée aux besoins qui chevauchent la semaine courante.",
                "validation",
            ),
        }
        code, message, error_kind = messages.get(
            str(reason or ""),
            (
                "demand_emergency_not_eligible",
                "La demande n'est pas admissible à la dérogation urgente.",
                "validation",
            ),
        )
        blocks[ACTION_EMERGENCY_PLAN] = DemandWorkflowBlock(
            code=code,
            message=message,
            error_kind=error_kind,
        )
        return blocks

    def _emergency_repository(self) -> EmergencyDemandRepositoryPort:
        repository = self._demands
        if not hasattr(repository, "activate_emergency_override") or not hasattr(
            repository, "clear_emergency_override"
        ):
            raise ApplicationOperationError(
                "La dérogation d'approbation urgente n'est pas disponible dans ce runtime.",
                code="demand_emergency_override_unavailable",
            )
        return cast(EmergencyDemandRepositoryPort, repository)

    def _emergency_periods(self, number: str) -> tuple[DemandPeriodReadModel, ...]:
        if self._periods is None:
            return ()
        return tuple(
            call_application_port(
                lambda: self._periods.list_for_demand(number),
                code_prefix="demand_emergency_periods",
                context={"demand_number": number},
            )
        )

    def emergency_override_command(
        self,
        command: DemandEmergencyOverrideCommand,
    ) -> dict[str, object]:
        number = self._required_identifier(command.number, entity="demand")
        reason = str(command.comment or "").strip()
        if not reason:
            raise ApplicationValidationError(
                "Une justification est requise pour planifier en urgence.",
                code="demand_emergency_comment_required",
                context={"demand_number": number},
            )

        existing = self._demand_or_not_found(number)
        self._assert_workflow_action(
            existing,
            ACTION_EMERGENCY_PLAN,
            expected_version=command.expected_version,
        )

        repository = self._emergency_repository()
        now = datetime.now(timezone.utc)
        with self._context("emergency demand override"):
            call_application_port(
                lambda: repository.activate_emergency_override(
                    number,
                    reason=reason,
                    actor_name=self._current_user,
                    occurred_at=now,
                    previous_status=existing.status,
                ),
                code_prefix="demand_emergency_override",
                context={"demand_number": number},
            )
        # 276C closes the historical emergency materialization bypass. Urgency may
        # remain an auditable treatment marker, but no human/asset plan is materialized
        # before the line-approval quorum is complete.
        return {}

    def approve_command(self, command):
        outcome = super().approve_command(command)
        if outcome.status == "En planification":
            repository = self._emergency_repository()
            call_application_port(
                lambda: repository.clear_emergency_override(
                    str(command.number or "").strip()
                ),
                code_prefix="demand_emergency_regularize",
                context={"demand_number": str(command.number or "").strip()},
            )
        return outcome


class EmergencyApplicationFacade(ApplicationFacade):
    def emergency_plan_demand(
        self,
        command: DemandEmergencyOverrideCommand,
    ) -> DemandMutationResult:
        service = cast(EmergencyDemandService, self._demands)
        summary = service.emergency_override_command(command)
        return DemandMutationResult(
            demand_number=command.number,
            status="Soumise",
            planning=PlanningResult.from_mapping(summary),
        )
