from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


TECHNICIAN_TYPE = "Technicien"
PROJECT_MANAGER_TYPE = "Chargé de projet"
BOTH_TYPE = "Technicien / Chargé de projet"


@dataclass(frozen=True)
class ContactCandidate:
    person_id: str
    person_type: str
    display_name: str


def default_display_name(person_id: str) -> str:
    """Return a friendly first-name style label without changing the matching key."""
    key = str(person_id or "").strip()
    if not key:
        return ""
    if "," in key:
        after_comma = key.split(",", 1)[1].strip()
        if after_comma:
            return after_comma.split()[0]
    return key.split()[0] if key.split() else key


def _technician_key(row: Mapping[str, Any]) -> str:
    return str(row.get("name") or row.get("Technicien") or "").strip()


def _manager_key(row: Mapping[str, Any]) -> str:
    return str(row.get("ChargeProjet") or "").strip()


def build_contact_candidates(
    technician_rows: Sequence[Mapping[str, Any]],
    demand_rows: Sequence[Mapping[str, Any]],
) -> tuple[ContactCandidate, ...]:
    """Build the explicit contact directory keys already used by planning data.

    Matching remains exact: ``person_id`` is never reformatted. Only the friendly
    display name is derived for use in email greetings.
    """
    roles: dict[str, set[str]] = {}

    for row in technician_rows:
        key = _technician_key(row)
        if key:
            roles.setdefault(key, set()).add(TECHNICIAN_TYPE)

    for row in demand_rows:
        key = _manager_key(row)
        if key:
            roles.setdefault(key, set()).add(PROJECT_MANAGER_TYPE)

    result: list[ContactCandidate] = []
    for key in sorted(roles, key=lambda value: value.casefold()):
        person_roles = roles[key]
        if person_roles == {TECHNICIAN_TYPE, PROJECT_MANAGER_TYPE}:
            person_type = BOTH_TYPE
        elif PROJECT_MANAGER_TYPE in person_roles:
            person_type = PROJECT_MANAGER_TYPE
        else:
            person_type = TECHNICIAN_TYPE
        result.append(
            ContactCandidate(
                person_id=key,
                person_type=person_type,
                display_name=default_display_name(key),
            )
        )
    return tuple(result)


def missing_contact_candidates(
    candidates: Sequence[ContactCandidate],
    existing_rows: Sequence[Mapping[str, Any]],
) -> tuple[ContactCandidate, ...]:
    existing = {
        str(row.get("PersonneCle") or "").strip()
        for row in existing_rows
        if str(row.get("PersonneCle") or "").strip()
    }
    return tuple(candidate for candidate in candidates if candidate.person_id not in existing)
