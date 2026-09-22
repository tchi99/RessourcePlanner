from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from .security import (
    PERMISSION_MANAGE_DEMANDS,
    UserIdentityRecord,
    permissions_for_roles,
)


@dataclass(frozen=True, slots=True)
class DemandRequesterReadModel:
    user_id: str
    display_name: str
    roles: tuple[str, ...]


class DemandRequesterDirectoryPort(Protocol):
    def list_users(self) -> Sequence[UserIdentityRecord]: ...

    def get_by_id(self, user_id: str) -> UserIdentityRecord | None: ...


def is_admissible_requester(record: UserIdentityRecord) -> bool:
    """Return whether an application user can legitimately own a demand."""

    return bool(
        record.active
        and PERMISSION_MANAGE_DEMANDS in permissions_for_roles(record.roles)
    )


class DemandRequesterService:
    """Read-only directory of stable requester identities exposed to demand forms."""

    def __init__(self, directory: DemandRequesterDirectoryPort) -> None:
        self._directory = directory

    def list_admissible(self) -> tuple[DemandRequesterReadModel, ...]:
        rows = (
            DemandRequesterReadModel(
                user_id=record.user_id,
                display_name=record.display_name,
                roles=tuple(record.roles),
            )
            for record in self._directory.list_users()
            if is_admissible_requester(record)
        )
        return tuple(
            sorted(
                rows,
                key=lambda row: (row.display_name.casefold(), row.user_id),
            )
        )
