from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .errors import ApplicationConflictError, ApplicationNotFoundError
from .security import AuthPrincipal, UserIdentityRecord


@dataclass(frozen=True, slots=True)
class DevUserIdentity:
    user_id: str
    display_name: str
    roles: tuple[str, ...]
    employee_external_id: str | None

    @classmethod
    def from_record(cls, record: UserIdentityRecord) -> "DevUserIdentity":
        return cls(
            user_id=record.user_id,
            display_name=record.display_name,
            roles=record.roles,
            employee_external_id=record.employee_external_id,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "user_id": self.user_id,
            "display_name": self.display_name,
            "roles": list(self.roles),
            "employee_external_id": self.employee_external_id,
        }


class DevUserRepositoryPort(Protocol):
    def list_users(self) -> tuple[UserIdentityRecord, ...]: ...

    def get_by_id(self, user_id: str) -> UserIdentityRecord | None: ...


class DevUserSwitcherService:
    """Resolve selectable development identities through the canonical AppUser model."""

    def __init__(self, repository: DevUserRepositoryPort) -> None:
        self._repository = repository

    def list_selectable_users(self) -> tuple[DevUserIdentity, ...]:
        return tuple(
            DevUserIdentity.from_record(record)
            for record in self._repository.list_users()
            if record.active
        )

    def select_user(self, user_id: str) -> AuthPrincipal:
        user_id_value = str(user_id or "").strip()
        record = self._repository.get_by_id(user_id_value)
        if record is None:
            raise ApplicationNotFoundError(
                "Identité de développement introuvable.",
                code="dev_user_not_found",
                context={"user_id": user_id_value},
            )
        if not record.active:
            raise ApplicationConflictError(
                "Cette identité de développement est inactive.",
                code="dev_user_inactive",
                context={"user_id": user_id_value},
            )
        return AuthPrincipal.from_roles(
            local_user_id=record.user_id,
            issuer=record.issuer,
            subject=record.subject,
            display_name=record.display_name,
            email=record.email,
            employee_external_id=record.employee_external_id,
            roles=record.roles,
            auth_mode="local",
        )
