from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...application.read_models import SegmentReadModel
from ...domain.active_days import normalize_active_day_target, split_total_workforce_hours
from ...domain.confirmation import CONFIRMATION_CONFIRMED, normalize_confirmation
from ...domain.planning_engine import MISSING_ALLOCATION_TYPE
from ...domain.planning_snapshot import PlanningSnapshot
from .models import Project, Resource, ResourceRequirement, Shift, WorkforceRequest
from .overallocation import (
    SqlPlannerQueryRepositoryWithOverallocation,
    SqlSegmentRepositoryWithAllocationMetrics,
)


INACTIVE_REQUIREMENT_STATUSES = {"Annulé", "Terminé"}


def _text(value: object) -> str:
    return str(value or "").strip()


def _identifier(requirement: ResourceRequirement) -> str:
    return _text(requirement.legacy_segment_id) or requirement.id


class SqlSegmentRepositoryWithActiveDayMetrics(SqlSegmentRepositoryWithAllocationMetrics):
    """Add derived active-day target diagnostics to the canonical segment read model."""

    def __init__(self, session: Session, *, actor_name: str = "") -> None:
        super().__init__(session, actor_name=actor_name)
        self._active_day_session = session

    def _active_day_metrics(self) -> dict[str, tuple[int, int]]:
        rows = self._active_day_session.execute(
            select(
                Shift.resource_requirement_id,
                Shift.work_date,
                Shift.locked,
            )
            .where(
                (Shift.allocation_type.is_(None))
                | (Shift.allocation_type != MISSING_ALLOCATION_TYPE)
            )
        ).all()
        all_days: dict[str, set[object]] = defaultdict(set)
        locked_days: dict[str, set[object]] = defaultdict(set)
        for requirement_id, work_date, locked in rows:
            all_days[requirement_id].add(work_date)
            if locked:
                locked_days[requirement_id].add(work_date)
        return {
            requirement_id: (
                len(days),
                len(locked_days.get(requirement_id, set())),
            )
            for requirement_id, days in all_days.items()
        }

    @staticmethod
    def _diagnostic(
        row: SegmentReadModel,
        *,
        planned_days: int,
        locked_days: int,
    ) -> str | None:
        target = row.desired_active_days
        if target is None or row.planning_type == "Fixe" or planned_days == target:
            return None
        if locked_days > target:
            return (
                f"{locked_days} jour(s) verrouillé(s) dépassent la cible de {target}; "
                "les décisions manuelles sont conservées."
            )
        if planned_days > target:
            return (
                f"La capacité disponible exige {planned_days} jour(s) actifs au lieu "
                f"de la cible de {target}."
            )
        return (
            f"Le plan utilise {planned_days} jour(s) actifs sur une cible de {target}; "
            "la capacité ou les heures verrouillées ne permettent pas de matérialiser davantage de jours utiles."
        )

    def _enrich_active_days(
        self,
        row: SegmentReadModel,
        metrics: tuple[int, int] | None,
    ) -> SegmentReadModel:
        planned_days, locked_days = metrics or (0, 0)
        target = row.desired_active_days
        target_met = (
            planned_days == target
            if target is not None and row.planning_type != "Fixe"
            else None
        )
        return replace(
            row,
            planned_active_days=planned_days,
            active_day_target_met=target_met,
            active_day_diagnostic=self._diagnostic(
                row,
                planned_days=planned_days,
                locked_days=locked_days,
            ),
        )

    def list(self, *, include_cancelled: bool = True):
        rows = super().list(include_cancelled=include_cancelled)
        requirements = self._active_day_session.scalars(select(ResourceRequirement)).all()
        reference_to_id = {
            _identifier(requirement): requirement.id for requirement in requirements
        }
        metrics = self._active_day_metrics()
        return tuple(
            self._enrich_active_days(
                row,
                metrics.get(reference_to_id.get(row.segment_id, "")),
            )
            for row in rows
        )

    def get(self, segment_id: str) -> SegmentReadModel | None:
        row = super().get(segment_id)
        if row is None:
            return None
        requirement = self._active_day_session.scalar(
            select(ResourceRequirement).where(
                (ResourceRequirement.id == _text(segment_id))
                | (ResourceRequirement.legacy_segment_id == _text(segment_id))
            )
        )
        if requirement is None:
            return row
        return self._enrich_active_days(
            row,
            self._active_day_metrics().get(requirement.id),
        )


class SqlPlannerQueryRepositoryWithEstimatedDays(
    SqlPlannerQueryRepositoryWithOverallocation
):
    """Canonical reads and plan-delta preview using #68 workforce-hour semantics."""

    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self._estimated_days_session = session
        self._segments = SqlSegmentRepositoryWithActiveDayMetrics(session)

    def _legacy_hours_per_resource(
        self,
        request: WorkforceRequest,
        desired: int,
        current: list[ResourceRequirement],
        proposed_resource: Resource | None,
        snapshot: PlanningSnapshot,
    ) -> float | None:
        del proposed_resource, snapshot
        if request.estimated_hours is not None and request.estimated_hours > 0:
            split = split_total_workforce_hours(request.estimated_hours, desired)
            return split[0] if split else None
        current_total = sum(
            float(row.planned_hours) for row in current if row.planned_hours > 0
        )
        if current_total > 0:
            split = split_total_workforce_hours(current_total, desired)
            return split[0] if split else None
        return None

    @staticmethod
    def _with_active_day_target(
        row: dict[str, object],
        target: int | None,
    ) -> dict[str, object]:
        return {**row, "JoursActifsCibles": target}

    def _proposed_segments(
        self,
        request: WorkforceRequest,
        current: list[ResourceRequirement],
        snapshot: PlanningSnapshot,
    ) -> list[dict[str, object]] | None:
        if bool(request.line_mode):
            return super()._proposed_segments(request, current, snapshot)

        project = self._estimated_days_session.get(Project, request.project_id)
        if project is None:
            return None
        resources = {
            row.id: row
            for row in self._estimated_days_session.scalars(select(Resource)).all()
        }
        period_key_by_requirement = self._period_key_by_requirement(request.id)
        periods = self._effective_periods(request.id)
        proposed: list[dict[str, object]] = []

        if periods:
            current_by_period: dict[str, list[ResourceRequirement]] = defaultdict(list)
            for requirement in current:
                key = period_key_by_requirement.get(requirement.id)
                if key:
                    current_by_period[key].append(requirement)

            for period in periods:
                ranked = sorted(
                    current_by_period.get(period.period_key, []),
                    key=lambda row: (
                        0 if row.assigned_resource_id else 1,
                        row.created_at,
                        row.id,
                    ),
                )
                desired = max(int(period.resource_count or 1), 1)
                split_hours = split_total_workforce_hours(period.hours, desired)
                inherited_confirmation = normalize_confirmation(period.confirmation)
                proposed_resource = resources.get(period.proposed_resource_id)
                for index in range(desired):
                    requirement = ranked[index] if index < len(ranked) else None
                    if requirement is not None and requirement.assigned_resource_id:
                        resource = resources.get(requirement.assigned_resource_id)
                    elif index == 0:
                        resource = proposed_resource
                    else:
                        resource = None
                    row = self._segment_row(
                        requirement=requirement,
                        request=request,
                        project=project,
                        resource=resource,
                        start_date=period.start_date,
                        end_date=period.end_date,
                        hours=split_hours[index],
                        confirmation=inherited_confirmation,
                        description=period.note or request.description,
                        synthetic_id=f"PREVIEW-{period.period_key}-{index + 1}",
                    )
                    proposed.append(
                        self._with_active_day_target(row, period.desired_active_days)
                    )
            return proposed

        if request.desired_start is None:
            return None
        desired = max(int(request.resource_count or 1), 1)
        proposed_resource = resources.get(request.proposed_resource_id)
        if request.estimated_hours is not None and request.estimated_hours > 0:
            total_hours = float(request.estimated_hours)
        else:
            total_hours = sum(
                float(row.planned_hours) for row in current if row.planned_hours > 0
            )
        if total_hours <= 0:
            return None
        split_hours = split_total_workforce_hours(total_hours, desired)
        try:
            target_days = normalize_active_day_target(
                request.estimated_days,
                start=request.desired_start,
                end=request.desired_end or request.desired_start,
                field="Les jours estimés de la demande",
            )
        except ValueError:
            return None

        ranked = sorted(
            current,
            key=lambda row: (
                0 if row.assigned_resource_id else 1,
                row.created_at,
                row.id,
            ),
        )
        inherited_confirmation = normalize_confirmation(
            request.confirmation,
            default=CONFIRMATION_CONFIRMED,
        )
        for index in range(desired):
            requirement = ranked[index] if index < len(ranked) else None
            if requirement is not None and requirement.assigned_resource_id:
                resource = resources.get(requirement.assigned_resource_id)
            elif index == 0:
                resource = proposed_resource
            else:
                resource = None
            row = self._segment_row(
                requirement=requirement,
                request=request,
                project=project,
                resource=resource,
                start_date=request.desired_start,
                end_date=request.desired_end or request.desired_start,
                hours=split_hours[index],
                confirmation=inherited_confirmation,
                description=request.description or "Ressource additionnelle",
                synthetic_id=f"PREVIEW-{request.id}-{index + 1}",
            )
            proposed.append(self._with_active_day_target(row, target_days))
        return proposed
