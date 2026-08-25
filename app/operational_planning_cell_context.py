from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable


@dataclass(frozen=True)
class CellContextBindings:
    """Dependencies required to evaluate one operational-planning cell."""

    segment_records: Callable[..., list[dict[str, Any]]]
    allocation_records: Callable[[Any], list[dict[str, Any]]]
    is_missing_allocation: Callable[[dict[str, Any]], bool]
    truthy: Callable[[Any], bool]
    number: Callable[[Any], float]
    availability_hours: Callable[[Any, str, date], float]
    parse_date: Callable[[Any], date | None]
    segment_dates: Callable[[dict[str, Any]], tuple[date | None, date | None]]
    resource_competence_map: Callable[[Any], dict[str, set[str]]]
    normalized_text: Callable[[Any], str]


@dataclass(frozen=True)
class OperationalPlanningCellContext:
    """Shared planning-cell calculations independent from historical V1.x modules."""

    bindings: CellContextBindings

    def segment_by_id(self, repo: Any, segment_id: str) -> dict[str, Any] | None:
        return next(
            (
                row
                for row in self.bindings.segment_records(repo, include_cancelled=False)
                if str(row.get("IDSegment") or "") == str(segment_id)
            ),
            None,
        )

    def locked_hours(
        self,
        repo: Any,
        segment_id: str,
        *,
        exclude_allocation: str | None = None,
    ) -> float:
        total = 0.0
        for row in self.bindings.allocation_records(repo):
            if str(row.get("IDSegment") or "") != str(segment_id):
                continue
            if exclude_allocation and str(row.get("IDAllocation") or "") == str(
                exclude_allocation
            ):
                continue
            if not self.bindings.truthy(row.get("Verrouillee")):
                continue
            if self.bindings.is_missing_allocation(row):
                continue
            total += self.bindings.number(row.get("Heures"))
        return round(total, 2)

    def validate_locked_total(
        self,
        repo: Any,
        segment_id: str,
        hours: Any,
        *,
        exclude_allocation: str | None = None,
    ) -> None:
        segment = self.segment_by_id(repo, segment_id)
        if not segment:
            return
        planned = self.bindings.number(segment.get("HeuresPrevues"))
        locked = self.locked_hours(
            repo,
            segment_id,
            exclude_allocation=exclude_allocation,
        )
        requested = self.bindings.number(hours)
        if locked + requested > planned + 0.01:
            raise ValueError(
                f"Les quarts verrouillés dépasseraient les {planned:g} h prévues du segment "
                f"({locked:g} h déjà verrouillées + {requested:g} h)."
            )

    def skill_message(
        self,
        repo: Any,
        technician: str,
        segment: dict[str, Any],
    ) -> tuple[str, bool]:
        required = str(segment.get("CompetenceRequise") or "").strip()
        if not required:
            return "Aucune compétence requise spécifiée.", True
        profile_skills = self.bindings.resource_competence_map(repo).get(
            technician,
            set(),
        )
        match = self.bindings.normalized_text(required) in profile_skills
        if match:
            return f"Compétence {required} attribuée à {technician}.", True
        return f"Attention : {required} n'est pas attribuée à {technician}.", False

    def day_standard_load(
        self,
        repo: Any,
        technician: str,
        day: date,
    ) -> tuple[float, float, float]:
        capacity = self.bindings.availability_hours(repo, technician, day)
        used = 0.0
        for row in self.bindings.allocation_records(repo):
            if self.bindings.is_missing_allocation(row):
                continue
            if str(row.get("Technicien") or "").strip() != technician:
                continue
            if self.bindings.parse_date(row.get("Date")) != day:
                continue
            if self.bindings.truthy(row.get("HorsHoraire")):
                continue
            used += self.bindings.number(row.get("Heures"))
        return (
            round(capacity, 2),
            round(used, 2),
            round(max(capacity - used, 0.0), 2),
        )

    def eligible_segments_for_cell(
        self,
        repo: Any,
        technician: str,
        day: date,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for segment in self.bindings.segment_records(repo, include_cancelled=False):
            if str(segment.get("Statut") or "") in {"Annulé", "Terminé"}:
                continue
            start, end = self.bindings.segment_dates(segment)
            if not start or not end or not (start <= day <= end):
                continue
            current_tech = str(segment.get("Technicien") or "").strip()
            if current_tech and current_tech != technician:
                continue
            segment_id = str(segment.get("IDSegment") or "")
            lockable = self.bindings.number(
                segment.get("HeuresPrevues")
            ) - self.locked_hours(repo, segment_id)
            if lockable <= 0.01:
                continue
            rows.append(segment)
        rows.sort(
            key=lambda row: (
                str(row.get("Priorite") or "Normale"),
                str(row.get("NumeroProjet") or ""),
                str(row.get("IDSegment") or ""),
            )
        )
        return rows
