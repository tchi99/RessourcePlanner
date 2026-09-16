from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping


def _text(value: Any) -> str:
    return str(value or "").strip()


def _optional_text(value: Any) -> str | None:
    normalized = _text(value)
    return normalized or None


def _date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def _optional_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return _number(value)


@dataclass(frozen=True, slots=True)
class DemandReadModel:
    """Storage-independent demand projection consumed by application/UI code."""

    number: str
    status: str
    project_number: str | None = None
    project_name: str | None = None
    client: str | None = None
    project_manager: str | None = None
    requester: str | None = None
    request_type: str | None = None
    priority: str | None = None
    confirmation: str | None = None
    desired_start: date | None = None
    desired_end: date | None = None
    description: str | None = None
    site_client: str | None = None
    location: str | None = None
    work_package_ref: str | None = None
    work_package_name: str | None = None
    resource_count: int = 1
    required_competencies: str | None = None
    estimated_hours: float | None = None
    estimated_days: float | None = None
    proposed_resource: str | None = None
    emergency_override_active: bool = False
    emergency_override_reason: str | None = None
    emergency_override_by: str | None = None
    emergency_override_at: datetime | None = None

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "DemandReadModel":
        return cls(
            number=_text(row.get("NoDemande")),
            status=_text(row.get("Statut")),
            project_number=_optional_text(row.get("NumeroProjet")),
            project_name=_optional_text(row.get("NomProjet")),
            client=_optional_text(row.get("Client")),
            project_manager=_optional_text(row.get("ChargeProjet")),
            requester=_optional_text(row.get("Demandeur")),
            request_type=_optional_text(row.get("TypeDemande")),
            priority=_optional_text(row.get("Priorite")),
            confirmation=_optional_text(row.get("Confirmation")),
            desired_start=_date(row.get("DateDebutSouhaitee")),
            desired_end=_date(row.get("DateFinSouhaitee")),
            description=_optional_text(row.get("Description")),
            site_client=_optional_text(row.get("SiteClient")),
            location=_optional_text(row.get("Lieu")),
            work_package_ref=_optional_text(row.get("SourceEffortID")),
            work_package_name=_optional_text(
                row.get("WorkPackageName") or row.get("NomEffort")
            ),
            resource_count=max(int(_number(row.get("NombreRessources")) or 1), 1),
            required_competencies=_optional_text(row.get("CompetencesRequises")),
            estimated_hours=_optional_number(row.get("TempsEstimeHeures")),
            estimated_days=_optional_number(row.get("TempsEstimeJours")),
            proposed_resource=_optional_text(row.get("TechnicienPropose")),
            emergency_override_active=bool(row.get("DerogationUrgenceActive") or False),
            emergency_override_reason=_optional_text(row.get("DerogationUrgenceRaison")),
            emergency_override_by=_optional_text(row.get("DerogationUrgencePar")),
        )


@dataclass(frozen=True, slots=True)
class DemandPeriodReadModel:
    """One versioned requested period/option under a workforce request."""

    period_id: str
    demand_number: str
    sequence: int
    kind: str
    start_date: date
    end_date: date
    hours: float
    confirmation: str
    alternative_group: str | None = None
    proposed_resource: str | None = None
    resource_count: int = 1
    note: str | None = None
    selected: bool = False


@dataclass(frozen=True, slots=True)
class SegmentReadModel:
    """Storage-independent operational requirement/segment projection.

    Project manager and requester are projections from the owning project/request. They
    are intentionally not authoritative segment fields, which keeps ownership aligned
    with the future Acumatica + WorkforceRequest sources of truth.
    """

    segment_id: str
    demand_number: str | None
    project_number: str | None
    project_name: str | None
    resource_name: str | None
    start_date: date | None
    end_date: date | None
    planned_hours: float
    status: str
    description: str | None = None
    origin: str | None = None
    required_competency: str | None = None
    planning_type: str | None = None
    priority: str | None = None
    outside_standard_hours: bool = False
    confirmation: str | None = None
    confirmation_overridden: bool = False
    project_manager: str | None = None
    requester: str | None = None

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "SegmentReadModel":
        return cls(
            segment_id=_text(row.get("IDSegment")),
            demand_number=_optional_text(row.get("NoDemande")),
            project_number=_optional_text(row.get("NumeroProjet")),
            project_name=_optional_text(row.get("NomProjet")),
            resource_name=_optional_text(row.get("Technicien")),
            start_date=_date(row.get("DateDebut")),
            end_date=_date(row.get("DateFin")),
            planned_hours=_number(row.get("HeuresPrevues")),
            status=_text(row.get("Statut")),
            description=_optional_text(row.get("Description")),
            origin=_optional_text(row.get("OrigineSegment")),
            required_competency=_optional_text(row.get("CompetenceRequise")),
            planning_type=_optional_text(row.get("TypePlanification")),
            priority=_optional_text(row.get("Priorite")),
            outside_standard_hours=bool(row.get("HorsHoraireAutorise") or False),
            confirmation=_optional_text(row.get("Confirmation")),
            confirmation_overridden=bool(row.get("ConfirmationOverride") or False),
            project_manager=_optional_text(
                row.get("ProjectManager") or row.get("ChargeProjet")
            ),
            requester=_optional_text(
                row.get("Requester") or row.get("Demandeur") or row.get("CreePar")
            ),
        )