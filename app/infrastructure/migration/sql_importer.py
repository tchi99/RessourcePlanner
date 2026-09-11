from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..sql.models import (
    Project,
    Resource,
    ResourceAvailabilityRule,
    ResourceRequirement,
    Shift,
    WorkforceRequest,
    WorkforceRequestHistory,
    WorkPackage,
)
from .excel_cutover import CutoverExtractionReport


CORE_MODELS = (
    Project,
    Resource,
    WorkPackage,
    WorkforceRequest,
    WorkforceRequestHistory,
    ResourceAvailabilityRule,
    ResourceRequirement,
    Shift,
)


class CutoverImportError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CutoverImportReport:
    source_counts: Mapping[str, int]
    sql_counts: Mapping[str, int]
    source_hours: Mapping[str, float]
    sql_hours: Mapping[str, float]
    mismatches: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.mismatches

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "source_counts": dict(self.source_counts),
            "sql_counts": dict(self.sql_counts),
            "source_hours": dict(self.source_hours),
            "sql_hours": dict(self.sql_hours),
            "mismatches": list(self.mismatches),
        }


def _text(value: object) -> str:
    return str(value or "").strip()


def _decimal(value: object | None) -> Decimal | None:
    if value in (None, ""):
        return None
    return Decimal(str(value).replace(",", "."))


def _required_decimal(value: object, *, entity: str, identifier: str) -> Decimal:
    result = _decimal(value)
    if result is None or result <= 0:
        raise CutoverImportError(
            f"{entity} {identifier}: les heures doivent être strictement positives."
        )
    return result


def _timestamp(value: object | None) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _count(session: Session, model: Any) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _assert_empty_database(session: Session) -> None:
    occupied: dict[str, int] = {}
    for model in CORE_MODELS:
        count = _count(session, model)
        if count > 0:
            occupied[model.__tablename__] = count
    if occupied:
        details = ", ".join(f"{name}={count}" for name, count in sorted(occupied.items()))
        raise CutoverImportError(
            "L'import final exige une base RessourcePlanner vide. Tables occupées: " + details
        )


def _sql_metrics(session: Session) -> tuple[dict[str, int], dict[str, float]]:
    counts = {
        "projects": _count(session, Project),
        "work_packages": _count(session, WorkPackage),
        "resources": _count(session, Resource),
        "availability": _count(session, ResourceAvailabilityRule),
        "demands": _count(session, WorkforceRequest),
        "history": _count(session, WorkforceRequestHistory),
        "requirements": _count(session, ResourceRequirement),
        "shifts": _count(session, Shift),
        "locked_shifts": int(
            session.scalar(
                select(func.count()).select_from(Shift).where(Shift.locked.is_(True))
            )
            or 0
        ),
    }
    hours = {
        "work_package_planned": float(
            session.scalar(select(func.coalesce(func.sum(WorkPackage.planned_hours), 0))) or 0
        ),
        "requirement_planned": float(
            session.scalar(select(func.coalesce(func.sum(ResourceRequirement.planned_hours), 0))) or 0
        ),
        "shift_total": float(
            session.scalar(select(func.coalesce(func.sum(Shift.hours), 0))) or 0
        ),
        "locked_shift_total": float(
            session.scalar(
                select(func.coalesce(func.sum(Shift.hours), 0)).where(Shift.locked.is_(True))
            )
            or 0
        ),
    }
    return counts, {key: round(value, 4) for key, value in hours.items()}


def _reconcile(
    source: CutoverExtractionReport,
    session: Session,
) -> CutoverImportReport:
    sql_counts, sql_hours = _sql_metrics(session)
    mismatches: list[str] = []
    for key, expected in source.counts.items():
        actual = sql_counts.get(key)
        if actual != expected:
            mismatches.append(f"count:{key}: source={expected} sql={actual}")
    for key, expected in source.hours.items():
        actual = sql_hours.get(key)
        if actual is None or abs(float(expected) - float(actual)) > 0.001:
            mismatches.append(f"hours:{key}: source={expected} sql={actual}")
    return CutoverImportReport(
        source_counts=dict(source.counts),
        sql_counts=sql_counts,
        source_hours=dict(source.hours),
        sql_hours=sql_hours,
        mismatches=tuple(mismatches),
    )


def _resolve_work_package(
    reference: str,
    by_legacy_id: Mapping[str, WorkPackage],
    by_source_row: Mapping[str, WorkPackage],
) -> WorkPackage | None:
    if not reference:
        return None
    return by_legacy_id.get(reference) or by_source_row.get(reference)


def import_cutover_dataset(
    session: Session,
    source: CutoverExtractionReport,
    *,
    demand_work_package_links: Mapping[str, str] | None = None,
    requirement_creator_names: Mapping[str, str] | None = None,
    require_empty: bool = True,
) -> CutoverImportReport:
    """Import one validated V1 snapshot into the caller-owned SQL transaction.

    This function never commits, rolls back, or rebuilds planning. The cutover caller
    owns the transaction and should commit only when the returned reconciliation is OK.
    """

    if source.blocking_errors:
        codes = ", ".join(sorted({row.code for row in source.blocking_errors}))
        raise CutoverImportError(
            f"Le préflight Excel contient {len(source.blocking_errors)} erreur(s) bloquante(s): {codes}"
        )
    if require_empty:
        _assert_empty_database(session)

    dataset = source.dataset
    demand_work_package_links = dict(demand_work_package_links or {})
    requirement_creator_names = dict(requirement_creator_names or {})

    projects: dict[str, Project] = {}
    for row in dataset.projects:
        number = _text(row.get("number"))
        project = Project(
            number=number,
            name=_text(row.get("name")),
            client=_text(row.get("client")) or None,
            project_manager_name=_text(row.get("project_manager")) or None,
            status=_text(row.get("status")) or "active",
        )
        session.add(project)
        projects[number] = project
    session.flush()

    resources: dict[str, Resource] = {}
    for row in dataset.resources:
        name = _text(row.get("name"))
        resource = Resource(
            name=name,
            resource_class=_text(row.get("resource_class")) or None,
            competencies=_text(row.get("competencies")) or None,
            note=_text(row.get("note")) or None,
            active=bool(row.get("active", True)),
            sort_order=int(row.get("sort_order") or 0),
        )
        session.add(resource)
        resources[name] = resource
    session.flush()

    work_packages_by_legacy: dict[str, WorkPackage] = {}
    work_packages_by_row: dict[str, WorkPackage] = {}
    for row in dataset.work_packages:
        identifier = _text(row.get("legacy_effort_id"))
        source_row = _text(row.get("source_row"))
        if identifier and identifier in work_packages_by_legacy:
            raise CutoverImportError(f"IDEffort dupliqué pendant l'import: {identifier}")
        if source_row and source_row in work_packages_by_row:
            raise CutoverImportError(f"Ligne effort dupliquée pendant l'import: {source_row}")
        project = projects[_text(row.get("project_number"))]
        work_package = WorkPackage(
            project_id=project.id,
            name=_text(row.get("name")) or "Effort",
            description=_text(row.get("description")) or None,
            start_date=row.get("start_date"),
            end_date=row.get("end_date"),
            planned_hours=_decimal(row.get("planned_hours")),
            status=_text(row.get("status")) or "planned",
            legacy_effort_id=identifier or None,
        )
        session.add(work_package)
        if identifier:
            work_packages_by_legacy[identifier] = work_package
        if source_row:
            work_packages_by_row[source_row] = work_package
    session.flush()

    for row in dataset.availability:
        resource_name = _text(row.get("resource_name"))
        resource = resources.get(resource_name) if resource_name else None
        session.add(
            ResourceAvailabilityRule(
                legacy_id=_text(row.get("legacy_id")) or None,
                resource_id=resource.id if resource is not None else None,
                availability_type=_text(row.get("availability_type")),
                start_date=row.get("start_date"),
                end_date=row.get("end_date"),
                weekdays=_text(row.get("weekdays")) or None,
                start_time=row.get("start_time"),
                end_time=row.get("end_time"),
                note=_text(row.get("note")) or None,
                active=bool(row.get("active", True)),
            )
        )
    session.flush()

    demands: dict[str, WorkforceRequest] = {}
    for row in dataset.demands:
        number = _text(row.get("number"))
        project = projects[_text(row.get("project_number"))]
        proposed = resources.get(_text(row.get("proposed_resource")))
        source_effort = _text(demand_work_package_links.get(number))
        linked_work_package = _resolve_work_package(
            source_effort,
            work_packages_by_legacy,
            work_packages_by_row,
        )
        if source_effort and linked_work_package is None:
            raise CutoverImportError(
                f"Demande {number}: SourceEffortID/SourceEffortRow introuvable: {source_effort}"
            )
        request = WorkforceRequest(
            legacy_demand_number=number,
            project_id=project.id,
            work_package_id=linked_work_package.id if linked_work_package else None,
            requester_name=_text(row.get("requester")) or None,
            request_type=_text(row.get("request_type")) or "Projet",
            priority=_text(row.get("priority")) or "Normale",
            confirmation=_text(row.get("confirmation")) or "Confirmée",
            desired_start=row.get("desired_start"),
            desired_end=row.get("desired_end"),
            description=_text(row.get("description")) or None,
            site_client=_text(row.get("site_client")) or None,
            location=_text(row.get("location")) or None,
            resource_count=int(row.get("resource_count") or 1),
            required_competencies=_text(row.get("required_competencies")) or None,
            estimated_hours=_decimal(row.get("estimated_hours")),
            estimated_days=_decimal(row.get("estimated_days")),
            proposed_resource_id=proposed.id if proposed else None,
            status=_text(row.get("status")) or "Brouillon",
            approved_by_name=_text(row.get("approved_by")) or None,
            approved_at=_timestamp(row.get("approved_at")),
            approval_comment=_text(row.get("approval_comment")) or None,
        )
        created_at = _timestamp(row.get("created_at"))
        updated_at = _timestamp(row.get("updated_at"))
        if created_at is not None:
            request.created_at = created_at
        if updated_at is not None:
            request.updated_at = updated_at
        session.add(request)
        demands[number] = request
    session.flush()

    for row in dataset.history:
        demand_number = _text(row.get("demand_number"))
        occurred_at = _timestamp(row.get("occurred_at"))
        if occurred_at is None:
            raise CutoverImportError(
                f"Historique {demand_number}: Horodatage manquant; aucune date ne sera inventée."
            )
        request = demands[demand_number]
        session.add(
            WorkforceRequestHistory(
                workforce_request_id=request.id,
                action=_text(row.get("action")) or "Historique",
                previous_status=_text(row.get("old_status")) or None,
                status=_text(row.get("new_status")) or None,
                comment=_text(row.get("comment")) or None,
                details=_text(row.get("details")) or None,
                actor_name=_text(row.get("actor")) or None,
                occurred_at=occurred_at,
            )
        )
    session.flush()

    requirements: dict[str, ResourceRequirement] = {}
    for row in dataset.requirements:
        identifier = _text(row.get("segment_id"))
        project = projects[_text(row.get("project_number"))]
        demand_number = _text(row.get("demand_number"))
        request = demands.get(demand_number) if demand_number else None
        resource = resources.get(_text(row.get("resource_name")))
        raw_source_effort = _text(row.get("source_effort_id"))
        source_work_package = _resolve_work_package(
            raw_source_effort,
            work_packages_by_legacy,
            work_packages_by_row,
        )
        if raw_source_effort and source_work_package is None:
            raise CutoverImportError(
                f"Segment {identifier}: SourceEffortID/SourceEffortRow introuvable: {raw_source_effort}"
            )
        canonical_source_effort = (
            _text(source_work_package.legacy_effort_id)
            if source_work_package is not None and source_work_package.legacy_effort_id
            else raw_source_effort
        )
        requirement = ResourceRequirement(
            legacy_segment_id=identifier,
            project_id=project.id,
            workforce_request_id=request.id if request else None,
            assigned_resource_id=resource.id if resource else None,
            start_date=row.get("start_date"),
            end_date=row.get("end_date"),
            planned_hours=_required_decimal(
                row.get("planned_hours"), entity="Segment", identifier=identifier
            ),
            status=_text(row.get("status")) or "À assigner",
            description=_text(row.get("description")) or None,
            source_effort_id=canonical_source_effort or None,
            required_competency=_text(row.get("required_competency")) or None,
            planning_type=_text(row.get("planning_type")) or "Flexible",
            priority=_text(row.get("priority")) or "Normale",
            outside_standard_hours_allowed=bool(
                row.get("outside_standard_hours_allowed", False)
            ),
            origin=_text(row.get("origin")) or "REQUEST",
            created_by_name=_text(requirement_creator_names.get(identifier)) or None,
        )
        created_at = _timestamp(row.get("created_at"))
        updated_at = _timestamp(row.get("updated_at"))
        if created_at is not None:
            requirement.created_at = created_at
        if updated_at is not None:
            requirement.updated_at = updated_at
        session.add(requirement)
        requirements[identifier] = requirement
    session.flush()

    for row in dataset.shifts:
        identifier = _text(row.get("allocation_id"))
        requirement = requirements[_text(row.get("segment_id"))]
        resource = resources[_text(row.get("resource_name"))]
        session.add(
            Shift(
                legacy_allocation_id=identifier,
                resource_requirement_id=requirement.id,
                resource_id=resource.id,
                work_date=row.get("work_date"),
                hours=_required_decimal(
                    row.get("hours"), entity="Quart", identifier=identifier
                ),
                allocation_type=_text(row.get("allocation_type")) or None,
                source=_text(row.get("source")) or "AUTO",
                locked=bool(row.get("locked", False)),
                outside_standard_hours=bool(
                    row.get("outside_standard_hours", False)
                ),
                confirmation=_text(row.get("confirmation")) or None,
                note=_text(row.get("note")) or None,
            )
        )
    session.flush()

    result = _reconcile(source, session)
    if not result.ok:
        raise CutoverImportError(
            "Réconciliation SQL échouée avant commit: " + "; ".join(result.mismatches)
        )
    return result
