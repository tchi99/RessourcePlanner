from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Protocol, Sequence

from .errors import ApplicationConflictError, ApplicationValidationError, call_application_port
from .resource_admin import (
    AVAILABILITY_STANDARD,
    AvailabilityRuleCreateCommand,
    ResourceAdminRepositoryPort,
    ResourceAdminService,
)


@dataclass(frozen=True, slots=True)
class BootstrapStandardSchedule:
    weekdays: str
    start_time: time
    end_time: time


@dataclass(frozen=True, slots=True)
class BootstrapResourceRecord:
    external_id: str
    name: str
    email: str | None
    active: bool
    resource_class: str
    sort_order: int | None = None
    standard_schedule: BootstrapStandardSchedule | None = None


class ResourceBootstrapSourcePort(Protocol):
    def list_resources(self) -> Sequence[BootstrapResourceRecord]: ...


@dataclass(frozen=True, slots=True)
class ResourceBootstrapResult:
    received: int
    created: int
    updated: int
    unchanged: int
    invalid: int
    schedules_created: int
    schedules_unchanged: int
    schedules_preserved: int
    without_schedule: int

    def to_dict(self) -> dict[str, int]:
        return {
            "received": self.received,
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "invalid": self.invalid,
            "schedules_created": self.schedules_created,
            "schedules_unchanged": self.schedules_unchanged,
            "schedules_preserved": self.schedules_preserved,
            "without_schedule": self.without_schedule,
        }


def _required(value: object, *, field: str, code: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ApplicationValidationError(
            f"{field} est requis pour le bootstrap des ressources.",
            code=code,
            context={"field": field},
        )
    return text


def _optional(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


class ResourceBootstrapService:
    """Temporary resource import preserving fields owned by local planning."""

    def __init__(
        self,
        source: ResourceBootstrapSourcePort,
        repository: ResourceAdminRepositoryPort,
    ) -> None:
        self._source = source
        self._repository = repository
        self._resource_admin = ResourceAdminService(repository)

    def synchronize(self) -> ResourceBootstrapResult:
        rows = tuple(self._source.list_resources())
        counts = {
            "created": 0,
            "updated": 0,
            "unchanged": 0,
            "schedules_created": 0,
            "schedules_unchanged": 0,
            "schedules_preserved": 0,
            "without_schedule": 0,
        }
        seen: set[str] = set()

        for item in rows:
            external_id = _required(
                item.external_id,
                field="external_id",
                code="resource_bootstrap_external_id_required",
            )
            name = _required(item.name, field="name", code="resource_bootstrap_name_required")
            resource_class = _required(
                item.resource_class,
                field="resource_class",
                code="resource_bootstrap_class_required",
            )
            if external_id in seen:
                raise ApplicationConflictError(
                    "Le même external_id apparaît plus d'une fois dans le bootstrap.",
                    code="resource_bootstrap_duplicate_external_id",
                    context={"external_id": external_id},
                )
            seen.add(external_id)
            if item.sort_order is not None and int(item.sort_order) < 0:
                raise ApplicationValidationError(
                    "L'ordre d'affichage ne peut pas être négatif.",
                    code="resource_bootstrap_sort_order_invalid",
                    context={"external_id": external_id},
                )

            matches = call_application_port(
                lambda: self._repository.find_resources_by_external_id(external_id),
                code_prefix="resource_bootstrap_read",
                context={"external_id": external_id},
            )
            if len(matches) > 1:
                raise ApplicationConflictError(
                    "Plusieurs ressources portent le même external_id.",
                    code="resource_bootstrap_external_id_collision",
                    context={"external_id": external_id, "count": len(matches)},
                )

            owned_values: dict[str, object] = {
                "name": name,
                "email": _optional(item.email),
                "active": bool(item.active),
                "resource_class": resource_class,
                "external_id": external_id,
            }
            if item.sort_order is not None:
                owned_values["sort_order"] = int(item.sort_order)

            if not matches:
                name_match = call_application_port(
                    lambda: self._repository.find_resource_by_name(name),
                    code_prefix="resource_bootstrap_read",
                    context={"name": name},
                )
                if name_match is not None and name_match.external_id is None:
                    raise ApplicationConflictError(
                        "Une ressource locale non liée porte déjà ce nom; confirmez son external_id explicitement avant l'import.",
                        code="resource_bootstrap_unlinked_name_conflict",
                        context={"external_id": external_id, "resource_id": name_match.id},
                    )
                resource_id = str(
                    call_application_port(
                        lambda: self._repository.create_resource(
                            {**owned_values, "sort_order": int(item.sort_order or 0)}
                        ),
                        code_prefix="resource_bootstrap_create",
                        context={"external_id": external_id},
                    )
                )
                counts["created"] += 1
            else:
                current = matches[0]
                resource_id = current.id
                changes = {
                    field: value
                    for field, value in owned_values.items()
                    if getattr(current, field) != value
                }
                if changes:
                    call_application_port(
                        lambda: self._repository.update_resource(resource_id, changes),
                        code_prefix="resource_bootstrap_update",
                        context={"external_id": external_id, "resource_id": resource_id},
                    )
                    counts["updated"] += 1
                else:
                    counts["unchanged"] += 1

            schedule = item.standard_schedule
            if schedule is None:
                counts["without_schedule"] += 1
                continue

            rules = call_application_port(
                lambda: self._repository.list_availability_rules(
                    resource_id=resource_id,
                    include_global=False,
                    active_only=True,
                ),
                code_prefix="resource_bootstrap_availability_read",
                context={"external_id": external_id, "resource_id": resource_id},
            )
            standards = tuple(
                rule for rule in rules if rule.availability_type == AVAILABILITY_STANDARD
            )
            if any(
                rule.start_date is None
                and rule.end_date is None
                and (rule.weekdays or "") == schedule.weekdays
                and rule.start_time == schedule.start_time
                and rule.end_time == schedule.end_time
                for rule in standards
            ):
                counts["schedules_unchanged"] += 1
                continue
            if standards:
                counts["schedules_preserved"] += 1
                continue

            self._resource_admin.create_availability_rule(
                AvailabilityRuleCreateCommand(
                    availability_type=AVAILABILITY_STANDARD,
                    resource_id=resource_id,
                    weekdays=schedule.weekdays,
                    start_time=schedule.start_time,
                    end_time=schedule.end_time,
                    note="Bootstrap #447",
                    active=True,
                )
            )
            counts["schedules_created"] += 1

        return ResourceBootstrapResult(
            received=len(rows),
            created=counts["created"],
            updated=counts["updated"],
            unchanged=counts["unchanged"],
            invalid=0,
            schedules_created=counts["schedules_created"],
            schedules_unchanged=counts["schedules_unchanged"],
            schedules_preserved=counts["schedules_preserved"],
            without_schedule=counts["without_schedule"],
        )
