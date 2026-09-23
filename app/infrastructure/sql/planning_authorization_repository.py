from __future__ import annotations

import json
from datetime import date
from collections.abc import Mapping, Sequence
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...application.errors import ApplicationConflictError
from ...application.repository_ports import PlanningAuthorizationPort
from ...application.security import ROLE_ADMIN, ROLE_COORDINATOR, ROLE_PROJECT_MANAGER
from .approval_revision_models import (
    APPROVAL_REFERENCE_CAPTURED,
    RequestApprovalReference,
    RequestApprovalRevision,
)
from .models import ORIGIN_REQUEST, Project, ResourceRequirement, WorkforceRequest
from .operational_choice_repository import SqlRequestOperationalChoiceRepository


_TOLERANCE_FACTOR = Decimal("1.20")


def _text(value: object) -> str:
    return str(value or "").strip()


def _decimal(value: object) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


class SqlRequestPlanningAuthorizationRepository(PlanningAuthorizationPort):
    """Protect request-origin planning commands with the active approved revision."""

    def __init__(
        self,
        session: Session,
        *,
        actor_name: str = "",
        roles: Sequence[str] | None = None,
    ) -> None:
        self._session = session
        self._actor_name = _text(actor_name)
        self._roles = tuple(
            _text(role).upper()
            for role in (roles or ())
            if _text(role)
        )
        self._operational = SqlRequestOperationalChoiceRepository(
            session,
            actor_name=self._actor_name,
        )

    def _actor_role(self) -> str | None:
        for role in (ROLE_ADMIN, ROLE_COORDINATOR, ROLE_PROJECT_MANAGER):
            if role in self._roles:
                return role
        return None

    def _request(self, number: object) -> WorkforceRequest | None:
        wanted = _text(number)
        if not wanted:
            return None
        return self._session.scalar(
            select(WorkforceRequest).where(
                (WorkforceRequest.id == wanted)
                | (WorkforceRequest.legacy_demand_number == wanted)
            )
        )

    def _requirement(self, segment_id: str) -> ResourceRequirement:
        wanted = _text(segment_id)
        requirement = self._session.scalar(
            select(ResourceRequirement).where(
                (ResourceRequirement.id == wanted)
                | (ResourceRequirement.legacy_segment_id == wanted)
            )
        )
        if requirement is None:
            raise KeyError(f"Segment {wanted} introuvable")
        return requirement

    @staticmethod
    def _entries(revision: RequestApprovalRevision) -> dict[str, dict[str, object]]:
        payload = json.loads(revision.payload_text)
        rows = payload.get("authorization", {}).get("entries", [])
        if not isinstance(rows, list):
            raise ValueError("Le snapshot approuvé ne contient pas d'entrées valides.")
        return {
            _text(row.get("identity")): dict(row)
            for row in rows
            if isinstance(row, Mapping) and _text(row.get("identity"))
        }

    def _approved_context(
        self,
        requirement: ResourceRequirement,
    ) -> tuple[WorkforceRequest, RequestApprovalRevision, dict[str, object]] | None:
        if (
            requirement.origin != ORIGIN_REQUEST
            or not requirement.workforce_request_id
        ):
            return None

        request = self._session.get(
            WorkforceRequest,
            requirement.workforce_request_id,
        )
        if request is None:
            raise ApplicationConflictError(
                "Le besoin est lié à une demande introuvable.",
                code="planning_authorization_unknown",
                context={"segment_id": _text(requirement.legacy_segment_id) or requirement.id},
            )

        reference = self._session.get(RequestApprovalReference, request.id)
        if (
            reference is None
            or reference.status != APPROVAL_REFERENCE_CAPTURED
            or not reference.active_revision_id
            or not requirement.approval_revision_id
            or requirement.approval_revision_id != reference.active_revision_id
            or requirement.approval_reference_status != APPROVAL_REFERENCE_CAPTURED
        ):
            raise ApplicationConflictError(
                "L'autorisation approuvée de ce besoin est inconnue. "
                "Une mutation qui élargit ou redéfinit le besoin doit passer par la demande.",
                code="planning_authorization_unknown",
                context={
                    "segment_id": _text(requirement.legacy_segment_id) or requirement.id,
                    "demand_number": _text(request.legacy_demand_number) or request.id,
                },
            )

        revision = self._session.get(
            RequestApprovalRevision,
            reference.active_revision_id,
        )
        entry_key = _text(requirement.approved_entry_key)
        entry = self._entries(revision).get(entry_key) if revision is not None else None
        if revision is None or not entry_key or entry is None:
            raise ApplicationConflictError(
                "Le besoin ne correspond à aucune entrée de l'autorisation approuvée active.",
                code="planning_authorization_entry_unknown",
                context={
                    "segment_id": _text(requirement.legacy_segment_id) or requirement.id,
                    "approved_entry_key": entry_key or None,
                },
            )
        return request, revision, entry

    @staticmethod
    def _same(value: object, current: object) -> bool:
        return _text(value) == _text(current)

    def authorize_segment_create(
        self,
        values: Mapping[str, object],
    ) -> None:
        origin = _text(values.get("OrigineSegment")) or ORIGIN_REQUEST
        if origin != ORIGIN_REQUEST:
            return
        request = self._request(values.get("NoDemande"))
        if request is None:
            return
        raise ApplicationConflictError(
            "La création directe d'un besoin lié à une demande ne peut pas inventer "
            "une nouvelle entrée d'autorisation. Modifie la demande ou utilise le "
            "chemin ad hoc prévu à cet effet.",
            code="planning_authorization_entry_required",
            context={
                "demand_number": _text(request.legacy_demand_number) or request.id,
            },
        )

    def authorize_segment_update(
        self,
        segment_id: str,
        updates: Mapping[str, object],
    ) -> None:
        requirement = self._requirement(segment_id)
        context = self._approved_context(requirement)
        if context is None:
            return

        request, _revision, _entry = context
        structural_changes: list[str] = []

        if "NoDemande" in updates:
            current_number = _text(request.legacy_demand_number) or request.id
            if _text(updates.get("NoDemande")) != current_number:
                structural_changes.append("NoDemande")
        if "NumeroProjet" in updates:
            project = self._session.get(Project, requirement.project_id)
            current_project = _text(project.number) if project is not None else requirement.project_id
            if _text(updates.get("NumeroProjet")) != current_project:
                structural_changes.append("NumeroProjet")
        if "DateDebut" in updates and updates.get("DateDebut") != requirement.start_date:
            structural_changes.append("DateDebut")
        if "DateFin" in updates and updates.get("DateFin") != requirement.end_date:
            structural_changes.append("DateFin")
        if (
            ("SourceEffortID" in updates or "SourceEffortRow" in updates)
            and _text(updates.get("SourceEffortID") or updates.get("SourceEffortRow"))
            != _text(requirement.source_effort_id)
        ):
            structural_changes.append("SourceEffortID")
        if (
            "ClasseRessourceRequise" in updates
            and not self._same(
                updates.get("ClasseRessourceRequise"),
                requirement.required_resource_class,
            )
        ):
            structural_changes.append("ClasseRessourceRequise")
        if (
            "CompetenceRequise" in updates
            and not self._same(
                updates.get("CompetenceRequise"),
                requirement.required_competency,
            )
        ):
            structural_changes.append("CompetenceRequise")

        if structural_changes:
            raise ApplicationConflictError(
                "La commande de planning modifierait la portée ou la fenêtre d'un "
                "besoin autorisé. Ces changements doivent passer par la demande.",
                code="planning_authorization_scope_change",
                context={
                    "segment_id": _text(requirement.legacy_segment_id) or requirement.id,
                    "fields": sorted(set(structural_changes)),
                    "approval_revision_id": requirement.approval_revision_id,
                    "approved_entry_key": requirement.approved_entry_key,
                },
            )

        if "HeuresPrevues" in updates:
            self.authorize_planned_hours(
                segment_id,
                float(updates["HeuresPrevues"]),
                explicit_increase=False,
            )

    def authorize_planned_hours(
        self,
        segment_id: str,
        planned_hours: float,
        *,
        explicit_increase: bool = False,
        expected_operational_version: int | None = None,
    ) -> None:
        requirement = self._requirement(segment_id)
        context = self._approved_context(requirement)
        if context is None:
            return
        request, revision, entry = context

        proposed = _decimal(planned_hours)
        if proposed <= 0:
            raise ValueError("Les heures prévues doivent être supérieures à zéro.")

        approved_total = _decimal(entry.get("hours"))
        slot_count = max(int(entry.get("slot_count") or 1), 1)
        if slot_count != 1 and proposed != _decimal(requirement.planned_hours):
            raise ApplicationConflictError(
                "Cette entrée approuvée couvre plusieurs slots. Une modification locale "
                "des heures doit passer par la demande afin de conserver le budget commun.",
                code="planning_authorization_multislot_change",
                context={
                    "segment_id": _text(requirement.legacy_segment_id) or requirement.id,
                    "approval_revision_id": revision.id,
                    "approved_entry_key": requirement.approved_entry_key,
                    "slot_count": slot_count,
                },
            )

        approved = approved_total
        current = _decimal(requirement.planned_hours)
        if proposed > approved and not explicit_increase:
            raise ApplicationConflictError(
                "Une hausse au-delà du budget approuvé exige l'intention explicite "
                "INCREASE_PLANNED ou une modification de la demande.",
                code="planning_authorization_increase_requires_explicit_policy",
                context={
                    "segment_id": _text(requirement.legacy_segment_id) or requirement.id,
                    "approved_hours": float(approved),
                    "current_hours": float(current),
                    "proposed_hours": float(proposed),
                },
            )

        if proposed > approved:
            role = self._actor_role()
            delegated_limit = (approved * _TOLERANCE_FACTOR).quantize(Decimal("0.01"))
            if role == ROLE_PROJECT_MANAGER and proposed <= delegated_limit:
                pass
            else:
                raise ApplicationConflictError(
                    "Cette hausse dépasserait l'autorisation approuvée active. "
                    "Modifie la demande afin qu'une nouvelle révision approuvée soit "
                    "créée; KEEP_EXCEPTION reste disponible pour conserver un excès "
                    "manuel sans augmenter le budget.",
                    code="planning_authorization_revision_required",
                    context={
                        "segment_id": _text(requirement.legacy_segment_id) or requirement.id,
                        "approval_revision_id": revision.id,
                        "approved_entry_key": requirement.approved_entry_key,
                        "approved_hours": float(approved),
                        "current_hours": float(current),
                        "proposed_hours": float(proposed),
                        "actor_role": role,
                        "delegated_limit_hours": float(delegated_limit),
                    },
                )

        demand_number = _text(request.legacy_demand_number) or request.id
        self._operational.set_budget_override(
            demand_number,
            _text(requirement.approved_entry_key),
            float(proposed),
            expected_version=expected_operational_version,
        )


    def operational_window_authorization(
        self,
        segment_id: str,
        target_day: date,
        *,
        expected_approval_revision_id: str | None = None,
    ) -> Mapping[str, object]:
        """Evaluate one local window against the exact active approved entry.

        This is deliberately narrower than approval-envelope comparison: it only
        answers whether the already-materialized requirement may widen to include
        the target day without changing authorization topology or borrowing another
        period/alternative.
        """

        requirement = self._requirement(segment_id)
        context = self._approved_context(requirement)
        if context is None:
            return {
                "authorized": True,
                "origin": requirement.origin,
                "approval_revision_id": None,
                "approved_entry_key": None,
                "approved_start": None,
                "approved_end": None,
            }

        _request, revision, entry = context
        expected = _text(expected_approval_revision_id)
        if expected and expected != revision.id:
            raise ApplicationConflictError(
                "L'autorisation approuvée du besoin a changé depuis l'évaluation.",
                code="planning_authorization_revision_conflict",
                context={
                    "expected_approval_revision_id": expected,
                    "current_approval_revision_id": revision.id,
                    "approved_entry_key": requirement.approved_entry_key,
                },
            )

        try:
            approved_start = date.fromisoformat(_text(entry.get("start_date")))
            approved_end = date.fromisoformat(_text(entry.get("end_date")))
        except ValueError as exc:
            raise ApplicationConflictError(
                "La fenêtre de l'entrée approuvée active est invalide.",
                code="planning_authorization_window_unknown",
                context={
                    "approval_revision_id": revision.id,
                    "approved_entry_key": requirement.approved_entry_key,
                },
            ) from exc

        return {
            "authorized": approved_start <= target_day <= approved_end,
            "origin": requirement.origin,
            "approval_revision_id": revision.id,
            "approved_entry_key": requirement.approved_entry_key,
            "approved_start": approved_start,
            "approved_end": approved_end,
        }
