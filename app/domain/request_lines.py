from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

DEFAULT_WORKDAY_HOURS = Decimal("8.00")
CENT = Decimal("0.01")


class RequestLinePolicyError(ValueError):
    def __init__(self, message: str, *, code: str, context: dict[str, object] | None = None):
        super().__init__(message)
        self.code = code
        self.context = context or {}


@dataclass(frozen=True, slots=True)
class NormalizedRequestLine:
    line_id: str | None
    position: int
    kind: str
    required_resource_class: str | None
    required_competency_ids: tuple[str, ...]
    required_competencies: str | None
    desired_start: date | None
    desired_end: date | None
    desired_active_days: int | None
    estimated_hours: float | None
    estimated_hours_source: str | None
    default_hours_per_day: float | None
    work_package_ref: str | None
    task_code: str | None
    proposed_resource_id: str | None
    confirmation: str
    description: str | None

    def to_repository_values(self) -> dict[str, object]:
        return {
            "id": self.line_id,
            "position": self.position,
            "kind": self.kind,
            "slot_count": 1,
            "required_resource_class": self.required_resource_class,
            "required_competency_ids": self.required_competency_ids,
            "required_competencies": self.required_competencies,
            "desired_start": self.desired_start,
            "desired_end": self.desired_end,
            "desired_active_days": self.desired_active_days,
            "estimated_hours": self.estimated_hours,
            "estimated_hours_source": self.estimated_hours_source,
            "default_hours_per_day": self.default_hours_per_day,
            "work_package_ref": self.work_package_ref,
            "task_code": self.task_code,
            "proposed_resource_id": self.proposed_resource_id,
            "confirmation": self.confirmation,
            "description": self.description,
        }


def _clean_optional(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def normalize_request_line(
    *,
    line_id: str | None,
    position: int,
    kind: str,
    required_resource_class: str | None,
    required_competency_ids: Iterable[str],
    required_competencies: str | None,
    desired_start: date | None,
    desired_end: date | None,
    desired_active_days: int | None,
    estimated_hours: float | None,
    work_package_ref: str | None,
    task_code: str | None,
    proposed_resource_id: str | None,
    confirmation: str,
    description: str | None,
    require_complete: bool,
) -> NormalizedRequestLine:
    normalized_kind = str(kind or "WORKFORCE").strip().upper()
    if normalized_kind != "WORKFORCE":
        raise RequestLinePolicyError(
            "Seules les lignes WORKFORCE sont supportées dans cette tranche.",
            code="demand_line_kind_unsupported",
            context={"kind": normalized_kind},
        )
    if position < 0:
        raise RequestLinePolicyError(
            "La position de ligne ne peut pas être négative.",
            code="demand_line_position_invalid",
            context={"position": position},
        )
    if desired_start is None and require_complete:
        raise RequestLinePolicyError(
            "La date de début est requise pour chaque ligne.",
            code="demand_line_start_required",
            context={"position": position},
        )
    if desired_start is not None and desired_end is not None and desired_end < desired_start:
        raise RequestLinePolicyError(
            "La date de fin d'une ligne ne peut pas précéder sa date de début.",
            code="demand_line_date_window_invalid",
            context={
                "position": position,
                "start": desired_start.isoformat(),
                "end": desired_end.isoformat(),
            },
        )
    if desired_active_days is not None:
        if int(desired_active_days) < 1:
            raise RequestLinePolicyError(
                "Le nombre de jours actifs d'une ligne doit être au moins 1.",
                code="demand_line_active_days_invalid",
                context={"position": position, "desired_active_days": desired_active_days},
            )
        if desired_start is not None:
            window_end = desired_end or desired_start
            available = (window_end - desired_start).days + 1
            if int(desired_active_days) > available:
                raise RequestLinePolicyError(
                    "Le nombre de jours actifs dépasse la fenêtre de la ligne.",
                    code="demand_line_active_days_window_invalid",
                    context={
                        "position": position,
                        "desired_active_days": int(desired_active_days),
                        "available_days": available,
                    },
                )

    hours_source: str | None = None
    default_hours_per_day: float | None = None
    normalized_hours: float | None = None
    if estimated_hours is not None:
        hours = Decimal(str(estimated_hours)).quantize(CENT, rounding=ROUND_HALF_UP)
        if hours <= 0:
            raise RequestLinePolicyError(
                "Les heures d'une ligne WORKFORCE doivent être supérieures à zéro.",
                code="demand_line_hours_invalid",
                context={"position": position, "estimated_hours": float(hours)},
            )
        normalized_hours = float(hours)
        hours_source = "EXPLICIT"
    elif desired_active_days is not None:
        hours = (Decimal(int(desired_active_days)) * DEFAULT_WORKDAY_HOURS).quantize(CENT)
        normalized_hours = float(hours)
        hours_source = "DEFAULT_8H"
        default_hours_per_day = float(DEFAULT_WORKDAY_HOURS)
    elif require_complete:
        raise RequestLinePolicyError(
            "Chaque ligne doit préciser des heures ou un nombre de jours actifs.",
            code="demand_line_effort_required",
            context={"position": position},
        )

    competency_ids = tuple(
        dict.fromkeys(str(value).strip() for value in required_competency_ids if str(value).strip())
    )
    return NormalizedRequestLine(
        line_id=_clean_optional(line_id),
        position=int(position),
        kind=normalized_kind,
        required_resource_class=_clean_optional(required_resource_class),
        required_competency_ids=competency_ids,
        required_competencies=_clean_optional(required_competencies),
        desired_start=desired_start,
        desired_end=desired_end,
        desired_active_days=int(desired_active_days) if desired_active_days is not None else None,
        estimated_hours=normalized_hours,
        estimated_hours_source=hours_source,
        default_hours_per_day=default_hours_per_day,
        work_package_ref=_clean_optional(work_package_ref),
        task_code=_clean_optional(task_code),
        proposed_resource_id=_clean_optional(proposed_resource_id),
        confirmation=str(confirmation or "Confirmée").strip() or "Confirmée",
        description=_clean_optional(description),
    )


def default_legacy_hours(
    *,
    estimated_hours: float | None,
    estimated_days: float | None,
    resource_count: int,
) -> float | None:
    if estimated_hours is not None:
        return float(estimated_hours)
    if estimated_days is None:
        return None
    days = Decimal(str(estimated_days))
    if days <= 0:
        return None
    return float((days * Decimal(max(int(resource_count), 1)) * DEFAULT_WORKDAY_HOURS).quantize(CENT))
