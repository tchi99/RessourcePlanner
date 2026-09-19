from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Protocol, Sequence, cast

from .demand_service import DemandService
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


def emergency_window(
    demand: DemandReadModel,
    periods: Sequence[DemandPeriodReadModel] = (),
) -> tuple[date, date] | None:
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
        if existing.line_mode:
            raise ApplicationOperationError(
                "La planification urgente des demandes multi-lignes sera activée avec #288E.",
                code="demand_line_emergency_unavailable",
                context={"demand_number": number},
            )
        periods = self._emergency_periods(number)
        eligible, eligibility_reason = emergency_override_eligibility(
            existing,
            today=self._today_provider(),
            periods=periods,
        )
        if not eligible:
            if eligibility_reason == "ALREADY_ACTIVE":
                raise ApplicationConflictError(
                    "Une dérogation urgente est déjà active. La demande doit être régularisée par l'approbation normale avant toute nouvelle dérogation.",
                    code="demand_emergency_override_already_active",
                    context={"demand_number": number},
                )
            messages = {
                "STATUS_NOT_SUBMITTED": "La dérogation urgente est réservée aux demandes Soumises.",
                "NOT_URGENT": "La demande doit être marquée Urgent pour utiliser cette dérogation.",
                "WINDOW_INCOMPLETE": "La fenêtre urgente ne peut pas être déterminée; sélectionner les alternatives requises ou compléter les dates.",
                "OUTSIDE_CURRENT_WEEK": "La dérogation urgente est limitée aux besoins qui chevauchent la semaine courante.",
            }
            raise ApplicationValidationError(
                messages.get(
                    eligibility_reason,
                    "La demande n'est pas admissible à la dérogation urgente.",
                ),
                code=f"demand_emergency_{str(eligibility_reason or 'not_eligible').lower()}",
                context={"demand_number": number},
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
            call_application_port(
                lambda: self._approved_sync.sync_approved(number),
                code_prefix="demand_emergency_sync",
                context={"demand_number": number},
            )
            summary = call_application_port(
                self._planning.rebuild,
                code_prefix="demand_emergency_rebuild",
                context={"demand_number": number},
            )
        return dict(summary)

    def approve_command(self, command):
        summary = super().approve_command(command)
        repository = self._emergency_repository()
        call_application_port(
            lambda: repository.clear_emergency_override(
                str(command.number or "").strip()
            ),
            code_prefix="demand_emergency_regularize",
            context={"demand_number": str(command.number or "").strip()},
        )
        return summary


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
