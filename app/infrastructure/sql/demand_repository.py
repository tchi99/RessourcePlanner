from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
import json
import re
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, aliased

from ...application.errors import ApplicationConflictError
from ...application.read_models import DemandLineReadModel, DemandReadModel
from ...application.repository_ports import DemandRepositoryPort
from .base import new_id, utc_now
from .models import (
    Competency,
    Project,
    RequestLine,
    RequestLineCompetency,
    Resource,
    TaskCatalogEntry,
    WorkforceRequest,
    WorkforceRequestCompetency,
    WorkforceRequestHistory,
    WorkPackage,
)


_DEMAND_NUMBER_RE = re.compile(r"^DMO-(\d{4})-(\d+)$", re.IGNORECASE)


def _text(value: object) -> str:
    return str(value or "").strip()


def _optional_text(value: object) -> str | None:
    value_text = _text(value)
    return value_text or None


def _decimal(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    return Decimal(str(value).replace(",", "."))


class SqlDemandRepository(DemandRepositoryPort):
    """SQLAlchemy implementation of the workforce-demand persistence port.

    The repository participates in the caller's transaction. It flushes mutations so
    constraints fail inside the use case, but it never commits or rolls back itself.
    """

    def __init__(
        self,
        session: Session,
        *,
        actor_name: str = "",
        actor_user_id: str | None = None,
    ) -> None:
        self._session = session
        self._actor_name = _text(actor_name)
        self._actor_user_id = _optional_text(actor_user_id)

    def _acquire_request_version(
        self,
        request: WorkforceRequest,
        expected_version: int,
    ) -> int:
        expected = int(expected_version)
        result = self._session.execute(
            update(WorkforceRequest)
            .where(
                WorkforceRequest.id == request.id,
                WorkforceRequest.aggregate_version == expected,
            )
            .values(aggregate_version=WorkforceRequest.aggregate_version + 1)
        )
        if int(result.rowcount or 0) != 1:
            actual = self._session.scalar(
                select(WorkforceRequest.aggregate_version).where(
                    WorkforceRequest.id == request.id
                )
            )
            raise ApplicationConflictError(
                "La demande a été modifiée depuis sa lecture.",
                code="demand_version_conflict",
                context={
                    "demand_number": _text(request.legacy_demand_number) or request.id,
                    "expected_version": expected,
                    "current_version": int(actual or request.aggregate_version or 1),
                },
            )
        self._session.flush()
        self._session.refresh(request, attribute_names=["aggregate_version"])
        return int(request.aggregate_version or expected + 1)

    def _read_model(
        self,
        request: WorkforceRequest,
        project: Project,
        work_package: WorkPackage | None,
        proposed_resource: Resource | None,
        competency_ids: tuple[str, ...] = (),
        lines: tuple[DemandLineReadModel, ...] = (),
    ) -> DemandReadModel:
        return DemandReadModel(
            # During the first SQL cutover the existing NoDemande is preserved in
            # legacy_demand_number. A dedicated business-number column can replace
            # this compatibility name later without changing the application port.
            number=_text(request.legacy_demand_number) or request.id,
            status=_text(request.status),
            project_number=_optional_text(project.number),
            project_name=_optional_text(project.name),
            client=_optional_text(project.client),
            project_manager=_optional_text(project.project_manager_name),
            requester_user_id=_optional_text(request.requester_user_id),
            requester=_optional_text(request.requester_name),
            priority=_optional_text(request.priority),
            confirmation=_optional_text(request.confirmation),
            desired_start=request.desired_start,
            desired_end=request.desired_end,
            description=_optional_text(request.description),
            work_package_ref=(
                _optional_text(work_package.legacy_effort_id) or work_package.id
                if work_package is not None
                else None
            ),
            work_package_name=(
                _optional_text(work_package.name) if work_package is not None else None
            ),
            task_code=_optional_text(request.erp_task_code),
            task_label=_optional_text(request.erp_task_label),
            resource_count=max(int(request.resource_count or 1), 1),
            required_competencies=_optional_text(request.required_competencies),
            required_competency_ids=competency_ids,
            estimated_hours=(
                float(request.estimated_hours)
                if request.estimated_hours is not None
                else None
            ),
            estimated_days=(
                float(request.estimated_days)
                if request.estimated_days is not None
                else None
            ),
            proposed_resource=(
                _optional_text(proposed_resource.name)
                if proposed_resource is not None
                else None
            ),
            version=max(int(request.aggregate_version or 1), 1),
            line_mode=bool(request.line_mode),
            lines=lines,
        )

    def _aggregate_children(
        self,
        request_ids: Sequence[str],
    ) -> tuple[
        dict[str, tuple[str, ...]],
        dict[str, tuple[DemandLineReadModel, ...]],
    ]:
        """Load request competencies and RequestLine projections in one batch query."""

        identifiers = tuple(str(value) for value in request_ids if str(value))
        if not identifiers:
            return {}, {}

        request_competency = aliased(WorkforceRequestCompetency)
        line_competency = aliased(RequestLineCompetency)
        proposed_resource = aliased(Resource)

        rows = self._session.execute(
            select(
                WorkforceRequest.id,
                RequestLine,
                WorkPackage,
                proposed_resource,
                request_competency.competency_id,
                line_competency.competency_id,
            )
            .select_from(WorkforceRequest)
            .outerjoin(
                RequestLine,
                RequestLine.workforce_request_id == WorkforceRequest.id,
            )
            .outerjoin(
                WorkPackage,
                RequestLine.work_package_id == WorkPackage.id,
            )
            .outerjoin(
                proposed_resource,
                RequestLine.proposed_resource_id == proposed_resource.id,
            )
            .outerjoin(
                request_competency,
                request_competency.workforce_request_id == WorkforceRequest.id,
            )
            .outerjoin(
                line_competency,
                line_competency.request_line_id == RequestLine.id,
            )
            .where(WorkforceRequest.id.in_(identifiers))
            .order_by(
                WorkforceRequest.id,
                RequestLine.position,
                RequestLine.id,
                request_competency.competency_id,
                line_competency.competency_id,
            )
        ).all()

        request_competencies: dict[str, set[str]] = {
            identifier: set() for identifier in identifiers
        }
        line_competencies: dict[str, set[str]] = {}
        line_rows: dict[
            str,
            tuple[str, RequestLine, WorkPackage | None, Resource | None],
        ] = {}

        for (
            request_id,
            line,
            work_package,
            resource,
            request_competency_id,
            line_competency_id,
        ) in rows:
            if request_competency_id is not None:
                request_competencies.setdefault(request_id, set()).add(
                    request_competency_id
                )
            if line is None:
                continue
            line_rows.setdefault(
                line.id,
                (request_id, line, work_package, resource),
            )
            if line_competency_id is not None:
                line_competencies.setdefault(line.id, set()).add(line_competency_id)

        grouped_lines: dict[str, list[DemandLineReadModel]] = {
            identifier: [] for identifier in identifiers
        }
        ordered_line_rows = sorted(
            line_rows.values(),
            key=lambda row: (
                row[0],
                int(row[1].position or 0),
                row[1].id,
            ),
        )
        for request_id, line, work_package, resource in ordered_line_rows:
            grouped_lines.setdefault(request_id, []).append(
                DemandLineReadModel(
                    line_id=line.id,
                    position=int(line.position or 0),
                    kind=_text(line.kind) or "WORKFORCE",
                    slot_count=max(int(line.slot_count or 1), 1),
                    required_resource_class=_optional_text(line.required_resource_class),
                    required_competencies=_optional_text(
                        line.required_competencies_snapshot
                    ),
                    required_competency_ids=tuple(
                        sorted(line_competencies.get(line.id, set()))
                    ),
                    desired_start=line.desired_start,
                    desired_end=line.desired_end,
                    desired_active_days=(
                        int(line.desired_active_days)
                        if line.desired_active_days is not None
                        else None
                    ),
                    estimated_hours=(
                        float(line.estimated_hours)
                        if line.estimated_hours is not None
                        else None
                    ),
                    estimated_hours_source=_optional_text(line.estimated_hours_source),
                    default_hours_per_day=(
                        float(line.default_hours_per_day)
                        if line.default_hours_per_day is not None
                        else None
                    ),
                    confirmation=_text(line.confirmation) or "Confirmée",
                    work_package_ref=(
                        _optional_text(work_package.legacy_effort_id) or work_package.id
                        if work_package is not None
                        else None
                    ),
                    work_package_name=(
                        _optional_text(work_package.name)
                        if work_package is not None
                        else None
                    ),
                    task_code=_optional_text(line.erp_task_code),
                    task_label=_optional_text(line.erp_task_label),
                    proposed_resource_id=_optional_text(line.proposed_resource_id),
                    proposed_resource=(
                        _optional_text(resource.name) if resource is not None else None
                    ),
                    description=_optional_text(line.description),
                    active=bool(line.active),
                )
            )

        return (
            {
                request_id: tuple(sorted(values))
                for request_id, values in request_competencies.items()
            },
            {
                request_id: tuple(values)
                for request_id, values in grouped_lines.items()
            },
        )

    def _row_query(self):
        proposed_resource = aliased(Resource)
        return (
            select(WorkforceRequest, Project, WorkPackage, proposed_resource)
            .join(Project, WorkforceRequest.project_id == Project.id)
            .outerjoin(WorkPackage, WorkforceRequest.work_package_id == WorkPackage.id)
            .outerjoin(
                proposed_resource,
                WorkforceRequest.proposed_resource_id == proposed_resource.id,
            )
        )

    def list(
        self,
        *,
        project_ids: Sequence[str] | None = None,
    ) -> Sequence[DemandReadModel]:
        statement = self._row_query()
        if project_ids is not None:
            identifiers = tuple(str(value) for value in project_ids if str(value))
            if not identifiers:
                return ()
            statement = statement.where(WorkforceRequest.project_id.in_(identifiers))
        rows = self._session.execute(
            statement.order_by(
                WorkforceRequest.desired_start,
                WorkforceRequest.legacy_demand_number,
                WorkforceRequest.id,
            )
        ).all()
        request_ids = tuple(
            request.id for request, _project, _work_package, _resource in rows
        )
        competency_ids, lines_by_request = self._aggregate_children(request_ids)
        return tuple(
            self._read_model(
                request,
                project,
                work_package,
                proposed_resource,
                competency_ids.get(request.id, ()),
                lines_by_request.get(request.id, ()),
            )
            for request, project, work_package, proposed_resource in rows
        )

    def get(self, number: str) -> DemandReadModel | None:
        wanted = _text(number)
        if not wanted:
            return None
        row = self._session.execute(
            self._row_query().where(
                (WorkforceRequest.legacy_demand_number == wanted)
                | (WorkforceRequest.id == wanted)
            )
        ).one_or_none()
        if row is None:
            return None
        request, project, work_package, proposed_resource = row
        competency_ids, lines_by_request = self._aggregate_children((request.id,))
        return self._read_model(
            request,
            project,
            work_package,
            proposed_resource,
            competency_ids.get(request.id, ()),
            lines_by_request.get(request.id, ()),
        )

    def _request(self, number: str) -> WorkforceRequest:
        wanted = _text(number)
        request = self._session.scalar(
            select(WorkforceRequest).where(
                (WorkforceRequest.legacy_demand_number == wanted)
                | (WorkforceRequest.id == wanted)
            )
        )
        if request is None:
            raise KeyError(f"Demande {wanted} introuvable")
        return request

    def _project(self, number: object) -> Project:
        project_number = _text(number)
        project = self._session.scalar(
            select(Project).where(Project.number == project_number)
        )
        if project is None:
            raise KeyError(f"Projet {project_number} introuvable")
        return project

    def _work_package(
        self,
        reference: object,
        *,
        project_id: str,
    ) -> WorkPackage | None:
        work_package_ref = _text(reference)
        if not work_package_ref:
            return None
        work_package = self._session.scalar(
            select(WorkPackage).where(
                (WorkPackage.id == work_package_ref)
                | (WorkPackage.legacy_effort_id == work_package_ref)
            )
        )
        if work_package is None:
            raise KeyError(f"Plage moyen terme {work_package_ref} introuvable")
        if work_package.project_id != project_id:
            raise ValueError(
                f"La plage moyen terme {work_package_ref} n'appartient pas au projet sélectionné."
            )
        return work_package

    def _task(self, code: object, *, project_number: str) -> TaskCatalogEntry | None:
        task_code = _text(code)
        if not task_code:
            return None
        task = self._session.scalar(
            select(TaskCatalogEntry).where(
                TaskCatalogEntry.project_number == _text(project_number),
                TaskCatalogEntry.task_code == task_code,
            )
        )
        if task is None:
            raise KeyError(
                f"Tâche ERP {_text(project_number)}/{task_code} introuvable"
            )
        if not task.active:
            raise ValueError(
                f"La tâche ERP {_text(project_number)}/{task_code} est inactive."
            )
        return task

    def _resource(self, name: object) -> Resource | None:
        resource_name = _text(name)
        if not resource_name:
            return None
        resource = self._session.scalar(
            select(Resource).where(Resource.name == resource_name)
        )
        if resource is None:
            raise KeyError(f"Ressource {resource_name} introuvable")
        return resource

    def _resource_by_id(self, identifier: object) -> Resource | None:
        resource_id = _text(identifier)
        if not resource_id:
            return None
        resource = self._session.get(Resource, resource_id)
        if resource is None:
            raise KeyError(f"Ressource {resource_id} introuvable")
        return resource

    def _competencies(self, identifiers: Sequence[str]) -> tuple[Competency, ...]:
        wanted = tuple(dict.fromkeys(_text(value) for value in identifiers if _text(value)))
        if not wanted:
            return ()
        rows = self._session.scalars(
            select(Competency).where(Competency.id.in_(wanted))
        ).all()
        by_id = {row.id: row for row in rows}
        missing = [identifier for identifier in wanted if identifier not in by_id]
        if missing:
            raise KeyError(f"Compétence {missing[0]} introuvable")
        inactive = [identifier for identifier in wanted if not by_id[identifier].active]
        if inactive:
            raise ValueError(f"Compétence {inactive[0]} inactive")
        return tuple(by_id[identifier] for identifier in wanted)

    def _replace_request_lines(
        self,
        request: WorkforceRequest,
        project: Project,
        values: Sequence[Mapping[str, Any]],
    ) -> tuple[RequestLine, ...]:
        existing = {
            line.id: line
            for line in self._session.scalars(
                select(RequestLine).where(
                    RequestLine.workforce_request_id == request.id
                )
            ).all()
        }
        seen: set[str] = set()
        active_lines: list[RequestLine] = []

        for index, raw in enumerate(values):
            supplied_id = _optional_text(raw.get("id"))
            line_id = supplied_id or new_id()
            if line_id in seen:
                raise ValueError(f"Identifiant de ligne dupliqué: {line_id}")
            seen.add(line_id)

            line = existing.get(line_id)
            if line is None:
                foreign = self._session.get(RequestLine, line_id)
                if foreign is not None:
                    raise ValueError(
                        f"La ligne {line_id} appartient à une autre demande."
                    )
                line = RequestLine(
                    id=line_id,
                    workforce_request_id=request.id,
                    position=index,
                    kind="WORKFORCE",
                )
                self._session.add(line)
            elif line.workforce_request_id != request.id:
                raise ValueError(
                    f"La ligne {line_id} appartient à une autre demande."
                )

            kind = _text(raw.get("kind")) or "WORKFORCE"
            if kind != "WORKFORCE":
                raise ValueError("Seules les lignes WORKFORCE sont supportées.")
            work_package = self._work_package(
                raw.get("work_package_ref"),
                project_id=project.id,
            )
            task = self._task(raw.get("task_code"), project_number=project.number)
            proposed = self._resource_by_id(raw.get("proposed_resource_id"))
            competencies = self._competencies(
                tuple(raw.get("required_competency_ids") or ())
            )

            line.position = int(raw.get("position") if raw.get("position") is not None else index)
            line.kind = kind
            line.slot_count = 1
            line.required_resource_class = _optional_text(
                raw.get("required_resource_class")
            )
            line.required_competencies_snapshot = _optional_text(
                raw.get("required_competencies")
            )
            line.desired_start = raw.get("desired_start")
            line.desired_end = raw.get("desired_end")
            line.desired_active_days = _decimal(raw.get("desired_active_days"))
            line.estimated_hours = _decimal(raw.get("estimated_hours"))
            line.estimated_hours_source = _optional_text(
                raw.get("estimated_hours_source")
            )
            line.default_hours_per_day = _decimal(raw.get("default_hours_per_day"))
            line.confirmation = _text(raw.get("confirmation")) or "Confirmée"
            line.work_package_id = work_package.id if work_package is not None else None
            line.task_catalog_item_id = task.id if task is not None else None
            line.erp_task_code = task.task_code if task is not None else None
            line.erp_task_label = task.label if task is not None else None
            line.proposed_resource_id = proposed.id if proposed is not None else None
            line.description = _optional_text(raw.get("description"))
            line.active = True

            self._session.execute(
                delete(RequestLineCompetency).where(
                    RequestLineCompetency.request_line_id == line.id
                )
            )
            self._session.add_all(
                [
                    RequestLineCompetency(
                        request_line_id=line.id,
                        competency_id=competency.id,
                    )
                    for competency in competencies
                ]
            )
            active_lines.append(line)

        for line_id, line in existing.items():
            if line_id not in seen:
                line.active = False

        self._session.execute(
            delete(WorkforceRequestCompetency).where(
                WorkforceRequestCompetency.workforce_request_id == request.id
            )
        )
        self._session.flush()
        self._sync_flat_summary_from_lines(request, active_lines)
        return tuple(active_lines)

    @staticmethod
    def _same_or_none(values: Sequence[object]) -> object | None:
        unique = {value for value in values}
        return next(iter(unique)) if len(unique) == 1 else None

    def _sync_flat_summary_from_lines(
        self,
        request: WorkforceRequest,
        lines: Sequence[RequestLine],
    ) -> None:
        if not lines:
            return
        starts = [line.desired_start for line in lines if line.desired_start is not None]
        ends = [
            line.desired_end or line.desired_start
            for line in lines
            if line.desired_start is not None
        ]
        request.desired_start = min(starts) if starts else None
        request.desired_end = max(ends) if ends else None
        request.resource_count = sum(max(int(line.slot_count or 1), 1) for line in lines)
        request.estimated_hours = (
            sum((line.estimated_hours or Decimal("0")) for line in lines)
            if all(line.estimated_hours is not None for line in lines)
            else None
        )
        request.estimated_days = (
            sum((line.desired_active_days or Decimal("0")) for line in lines)
            if all(line.desired_active_days is not None for line in lines)
            else None
        )
        snapshots = tuple(
            dict.fromkeys(
                _text(line.required_competencies_snapshot)
                for line in lines
                if _text(line.required_competencies_snapshot)
            )
        )
        request.required_competencies = "; ".join(snapshots) or None
        confirmations = [line.confirmation for line in lines]
        request.confirmation = (
            str(self._same_or_none(confirmations) or "Tentative")
        )
        request.work_package_id = self._same_or_none(
            [line.work_package_id for line in lines]
        )
        task_code = self._same_or_none([line.erp_task_code for line in lines])
        request.erp_task_code = str(task_code) if task_code is not None else None
        task_label = self._same_or_none([line.erp_task_label for line in lines])
        request.erp_task_label = str(task_label) if task_label is not None else None
        request.proposed_resource_id = (
            lines[0].proposed_resource_id if len(lines) == 1 else None
        )

    def _sync_legacy_request_line(
        self,
        request: WorkforceRequest,
        *,
        hours_source: str | None = None,
    ) -> RequestLine:
        """Mirror the current flat request into its transitional single line.

        288B does not expose multi-line writes yet. This keeps requests created or
        edited between the schema rollout and 288C coherent without making the line
        authoritative prematurely.
        """

        line = self._session.get(RequestLine, request.id)
        if line is None:
            line = RequestLine(
                id=request.id,
                workforce_request_id=request.id,
                position=0,
                kind="WORKFORCE",
            )
            self._session.add(line)

        project = self._session.get(Project, request.project_id)
        task_id = None
        if project is not None and request.erp_task_code:
            task_id = self._session.scalar(
                select(TaskCatalogEntry.id).where(
                    TaskCatalogEntry.project_number == project.number,
                    TaskCatalogEntry.task_code == request.erp_task_code,
                )
            )

        line.slot_count = max(int(request.resource_count or 1), 1)
        line.required_competencies_snapshot = request.required_competencies
        line.desired_start = request.desired_start
        line.desired_end = request.desired_end
        line.desired_active_days = request.estimated_days
        line.estimated_hours = request.estimated_hours
        if hours_source:
            line.estimated_hours_source = _text(hours_source)
            line.default_hours_per_day = (
                Decimal("8.00")
                if _text(hours_source) == "DEFAULT_8H"
                else None
            )
        elif line.estimated_hours_source is None and request.estimated_hours is not None:
            line.estimated_hours_source = "LEGACY"
        line.confirmation = request.confirmation
        line.work_package_id = request.work_package_id
        line.task_catalog_item_id = task_id
        line.erp_task_code = request.erp_task_code
        line.erp_task_label = request.erp_task_label
        line.proposed_resource_id = request.proposed_resource_id
        line.description = request.description
        line.active = True
        return line

    def _next_request_number(self) -> str:
        year = date.today().year
        prefix = f"DMO-{year}-"
        numbers = self._session.scalars(
            select(WorkforceRequest.legacy_demand_number).where(
                WorkforceRequest.legacy_demand_number.like(f"{prefix}%")
            )
        ).all()
        max_sequence = 0
        for number in numbers:
            match = _DEMAND_NUMBER_RE.match(_text(number))
            if match and int(match.group(1)) == year:
                max_sequence = max(max_sequence, int(match.group(2)))
        return f"DMO-{year}-{max_sequence + 1:04d}"

    def create(self, values: Mapping[str, Any], *, submit: bool = False) -> str:
        project = self._project(values.get("NumeroProjet"))
        work_package = self._work_package(
            values.get("SourceEffortID"),
            project_id=project.id,
        )
        task = self._task(
            values.get("TaskCode"),
            project_number=project.number,
        )
        proposed_resource = self._resource(values.get("TechnicienPropose"))
        number = self._next_request_number()
        status = "Soumise" if submit else "Brouillon"

        request = WorkforceRequest(
            legacy_demand_number=number,
            project_id=project.id,
            work_package_id=work_package.id if work_package is not None else None,
            erp_task_code=task.task_code if task is not None else None,
            erp_task_label=task.label if task is not None else None,
            requester_user_id=_optional_text(values.get("RequesterUserId")),
            # Canonical Web callers provide RequesterUserId and a server-derived
            # display snapshot. Legacy callers may still provide only Demandeur.
            # preserve the historical behavior and default to the authenticated actor.
            requester_name=_optional_text(values.get("Demandeur")) or self._actor_name or None,
            request_type=_text(values.get("TypeDemande")) or "Projet",
            priority=_text(values.get("Priorite")) or "Normale",
            confirmation=_text(values.get("Confirmation")) or "Confirmée",
            desired_start=values.get("DateDebutSouhaitee"),
            desired_end=values.get("DateFinSouhaitee"),
            description=_optional_text(values.get("Description")),
            site_client=_optional_text(values.get("SiteClient")),
            location=_optional_text(values.get("Lieu")),
            resource_count=int(values.get("NombreRessources") or 1),
            required_competencies=_optional_text(values.get("CompetencesRequises")),
            estimated_hours=_decimal(values.get("TempsEstimeHeures")),
            estimated_days=_decimal(values.get("TempsEstimeJours")),
            proposed_resource_id=proposed_resource.id if proposed_resource else None,
            status=status,
        )
        self._session.add(request)
        self._session.flush()
        request_lines = values.get("RequestLines")
        if request_lines is not None:
            request.line_mode = True
            self._replace_request_lines(
                request,
                project,
                tuple(request_lines),
            )
        else:
            self._sync_legacy_request_line(
                request,
                hours_source=_optional_text(values.get("RequestLineHoursSource")),
            )
        self._session.flush()
        self._append_history(
            request,
            action="Création",
            comment="Demande créée et soumise" if submit else "Demande créée",
            changed_fields=("create",),
        )
        self._session.flush()
        return number

    def extend_candidate_window(
        self,
        number: str,
        target_day: date,
        *,
        request_line_id: str | None = None,
        expected_version: int,
        action: str,
        comment: str = "",
    ) -> bool:
        request = self._request(number)
        current_version = int(request.aggregate_version or 1)
        self._acquire_request_version(request, expected_version)

        previous_status = request.status
        changed_fields: tuple[str, ...]
        if bool(request.line_mode):
            wanted = _text(request_line_id)
            if not wanted:
                raise KeyError("La ligne candidate est requise.")
            line = self._session.scalar(
                select(RequestLine).where(
                    RequestLine.id == wanted,
                    RequestLine.workforce_request_id == request.id,
                    RequestLine.active.is_(True),
                )
            )
            if line is None or line.desired_start is None:
                raise KeyError(f"Ligne {wanted} introuvable pour la demande.")
            proposed_start = min(line.desired_start, target_day)
            proposed_end = max(line.desired_end or line.desired_start, target_day)
            if proposed_start == line.desired_start and proposed_end == line.desired_end:
                return False
            line.desired_start = proposed_start
            line.desired_end = proposed_end
            active_lines = tuple(
                self._session.scalars(
                    select(RequestLine)
                    .where(
                        RequestLine.workforce_request_id == request.id,
                        RequestLine.active.is_(True),
                    )
                    .order_by(RequestLine.position, RequestLine.id)
                ).all()
            )
            self._sync_flat_summary_from_lines(request, active_lines)
            changed_fields = (f"RequestLine[{wanted}].DateWindow",)
        else:
            if request.desired_start is None:
                raise KeyError("La fenêtre candidate de la demande est incomplète.")
            proposed_start = min(request.desired_start, target_day)
            proposed_end = max(request.desired_end or request.desired_start, target_day)
            if proposed_start == request.desired_start and proposed_end == request.desired_end:
                return False
            request.desired_start = proposed_start
            request.desired_end = proposed_end
            self._sync_legacy_request_line(request)
            changed_fields = ("DateDebutSouhaitee", "DateFinSouhaitee")

        self._session.flush()
        self._append_history(
            request,
            action=_text(action) or "Modification",
            comment=_text(comment),
            previous_status=previous_status,
            changed_fields=changed_fields,
        )
        self._session.flush()
        return True

    def update(
        self,
        number: str,
        updates: Mapping[str, Any],
        *,
        action: str,
        comment: str = "",
    ) -> None:
        request = self._request(number)
        previous_status = request.status
        request_lines = updates.get("RequestLines")
        expected_version = updates.get("ExpectedVersion")
        guarded_version = expected_version is not None
        if expected_version is not None:
            self._acquire_request_version(request, int(expected_version))

        line_owned_flat_fields = {
            "SourceEffortID",
            "TaskCode",
            "Confirmation",
            "DateDebutSouhaitee",
            "DateFinSouhaitee",
            "NombreRessources",
            "CompetencesRequises",
            "TempsEstimeHeures",
            "TempsEstimeJours",
            "TechnicienPropose",
        }
        if (
            request_lines is None
            and bool(request.line_mode)
            and line_owned_flat_fields.intersection(updates)
        ):
            raise ValueError(
                "Les champs de besoin plats ne peuvent pas modifier une demande gérée par lignes."
            )

        project_changed = "NumeroProjet" in updates
        if project_changed and request_lines is None and bool(request.line_mode):
            raise ValueError(
                "Le changement de projet d'une demande gérée par lignes doit fournir lines."
            )
        if project_changed:
            request.project_id = self._project(updates.get("NumeroProjet")).id

        if "SourceEffortID" in updates:
            work_package = self._work_package(
                updates.get("SourceEffortID"),
                project_id=request.project_id,
            )
            request.work_package_id = work_package.id if work_package is not None else None
        elif project_changed and request.work_package_id:
            current_work_package = self._session.get(WorkPackage, request.work_package_id)
            if (
                current_work_package is None
                or current_work_package.project_id != request.project_id
            ):
                # A WorkPackage is project-owned. Changing project without explicitly
                # choosing a compatible WorkPackage must not leave a cross-project link.
                request.work_package_id = None

        if "TaskCode" in updates:
            project = self._session.get(Project, request.project_id)
            if project is None:
                raise KeyError("Projet de la demande introuvable")
            task = self._task(
                updates.get("TaskCode"),
                project_number=project.number,
            )
            request.erp_task_code = task.task_code if task is not None else None
            request.erp_task_label = task.label if task is not None else None
        elif project_changed:
            # A task code is project-scoped in the ERP export. Never keep a task
            # silently attached when the demand moves to another project.
            request.erp_task_code = None
            request.erp_task_label = None

        if "RequesterUserId" in updates:
            request.requester_user_id = _optional_text(updates.get("RequesterUserId"))
        if "Demandeur" in updates:
            request.requester_name = _optional_text(updates.get("Demandeur"))
        if "TypeDemande" in updates:
            request.request_type = _text(updates.get("TypeDemande")) or "Projet"
        if "Priorite" in updates:
            request.priority = _text(updates.get("Priorite")) or "Normale"
        if "Confirmation" in updates:
            request.confirmation = _text(updates.get("Confirmation")) or "Confirmée"
        if "DateDebutSouhaitee" in updates:
            request.desired_start = updates.get("DateDebutSouhaitee")
        if "DateFinSouhaitee" in updates:
            request.desired_end = updates.get("DateFinSouhaitee")
        if "Description" in updates:
            request.description = _optional_text(updates.get("Description"))
        if "SiteClient" in updates:
            request.site_client = _optional_text(updates.get("SiteClient"))
        if "Lieu" in updates:
            request.location = _optional_text(updates.get("Lieu"))
        if "NombreRessources" in updates:
            request.resource_count = int(updates.get("NombreRessources") or 1)
        if "CompetencesRequises" in updates:
            request.required_competencies = _optional_text(
                updates.get("CompetencesRequises")
            )
        if "TempsEstimeHeures" in updates:
            request.estimated_hours = _decimal(updates.get("TempsEstimeHeures"))
        if "TempsEstimeJours" in updates:
            request.estimated_days = _decimal(updates.get("TempsEstimeJours"))
        if "TechnicienPropose" in updates:
            proposed = self._resource(updates.get("TechnicienPropose"))
            request.proposed_resource_id = proposed.id if proposed else None
        if "Statut" in updates:
            request.status = _text(updates.get("Statut"))
        if "ApprouvePar" in updates:
            request.approved_by_name = _optional_text(updates.get("ApprouvePar"))
        if "DateApprobation" in updates:
            approved_at = updates.get("DateApprobation")
            request.approved_at = approved_at if isinstance(approved_at, datetime) else None
        if "CommentaireApprobation" in updates:
            request.approval_comment = _optional_text(
                updates.get("CommentaireApprobation")
            )

        # NomProjet/Client/ChargeProjet intentionally remain project-owned. They are
        # projected from projects and will ultimately be mastered by Acumatica.
        if request_lines is not None:
            request.line_mode = True
            project = self._session.get(Project, request.project_id)
            if project is None:
                raise KeyError("Projet de la demande introuvable")
            self._replace_request_lines(request, project, tuple(request_lines))
        elif not bool(request.line_mode):
            self._sync_legacy_request_line(
                request,
                hours_source=_optional_text(updates.get("RequestLineHoursSource")),
            )
        if not guarded_version:
            request.aggregate_version = int(request.aggregate_version or 1) + 1
        self._session.flush()
        self._append_history(
            request,
            action=_text(action) or "Modification",
            comment=_text(comment),
            previous_status=previous_status,
            changed_fields=tuple(
                sorted(
                    str(field)
                    for field in updates
                    if str(field) != "ExpectedVersion"
                )
            ),
        )
        self._session.flush()

    def _append_history(
        self,
        request: WorkforceRequest,
        *,
        action: str,
        comment: str,
        previous_status: str | None = None,
        changed_fields: tuple[str, ...] = (),
    ) -> None:
        details = json.dumps(
            {
                "aggregate_version": int(request.aggregate_version or 1),
                "line_mode": bool(request.line_mode),
                "changed_fields": list(dict.fromkeys(changed_fields)),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        self._session.add(
            WorkforceRequestHistory(
                workforce_request_id=request.id,
                action=action,
                previous_status=previous_status,
                status=request.status,
                comment=comment or None,
                details=details,
                actor_user_id=self._actor_user_id,
                actor_name=self._actor_name or None,
                occurred_at=utc_now(),
            )
        )
