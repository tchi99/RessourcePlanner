from __future__ import annotations

from typing import Protocol

from .errors import ApplicationConflictError, ApplicationNotFoundError, ApplicationValidationError
from .security import UserIdentityRecord


class IdentityResourceLinkRepositoryPort(Protocol):
    def get_user_by_id(self, user_id: str) -> UserIdentityRecord | None: ...

    def get_user_by_employee_external_id(
        self,
        employee_external_id: str,
    ) -> UserIdentityRecord | None: ...

    def resource_exists_by_external_id(self, employee_external_id: str) -> bool: ...

    def set_employee_external_id(
        self,
        user_id: str,
        employee_external_id: str | None,
    ) -> UserIdentityRecord: ...


class IdentityResourceLinkService:
    """Manage the explicit AppUser ↔ ResourceProfile link by stable ERP employee ID."""

    def __init__(self, repository: IdentityResourceLinkRepositoryPort) -> None:
        self._repository = repository

    def link(self, *, user_id: str, employee_external_id: str) -> UserIdentityRecord:
        user_id_value = str(user_id or "").strip()
        external_id = str(employee_external_id or "").strip()
        if not user_id_value or not external_id:
            raise ApplicationValidationError(
                "L'utilisateur et l'identifiant employé externe sont requis.",
                code="identity_resource_link_required",
            )
        user = self._repository.get_user_by_id(user_id_value)
        if user is None:
            raise ApplicationNotFoundError(
                "Utilisateur RessourcePlanner introuvable.",
                code="identity_resource_user_not_found",
                context={"user_id": user_id_value},
            )
        if not self._repository.resource_exists_by_external_id(external_id):
            raise ApplicationNotFoundError(
                "Aucune ressource synchronisée ne correspond à cet identifiant employé externe.",
                code="identity_resource_resource_not_found",
                context={"employee_external_id": external_id},
            )
        other = self._repository.get_user_by_employee_external_id(external_id)
        if other is not None and other.user_id != user_id_value:
            raise ApplicationConflictError(
                "Cette ressource est déjà liée à un autre utilisateur.",
                code="identity_resource_already_linked",
                context={"employee_external_id": external_id},
            )
        return self._repository.set_employee_external_id(user_id_value, external_id)

    def unlink(self, *, user_id: str) -> UserIdentityRecord:
        user_id_value = str(user_id or "").strip()
        if not user_id_value:
            raise ApplicationValidationError(
                "L'utilisateur est requis.",
                code="identity_resource_link_required",
            )
        if self._repository.get_user_by_id(user_id_value) is None:
            raise ApplicationNotFoundError(
                "Utilisateur RessourcePlanner introuvable.",
                code="identity_resource_user_not_found",
                context={"user_id": user_id_value},
            )
        return self._repository.set_employee_external_id(user_id_value, None)
