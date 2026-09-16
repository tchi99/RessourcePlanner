from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .security import (
    AuthPrincipal,
    IdentityService,
    ROLE_TECHNICIAN,
    UserIdentityRecord,
    UserIdentityRepositoryPort,
)


class IdentityProvisioningRepositoryPort(UserIdentityRepositoryPort, Protocol):
    def upsert(
        self,
        *,
        issuer: str,
        subject: str,
        display_name: str,
        email: str | None,
        roles: tuple[str, ...] | list[str] | set[str],
        active: bool = True,
        employee_external_id: str | None = None,
    ) -> UserIdentityRecord: ...


@dataclass(frozen=True, slots=True)
class AutoProvisioningPolicy:
    """Explicit opt-in policy for first-login provisioning.

    Until the real Acumatica contract is validated, the only permitted automatic
    role is TECHNICIAN (read-only). A disabled policy preserves the existing
    fail-closed behavior for unknown identities.
    """

    enabled: bool = False
    default_role: str = ROLE_TECHNICIAN

    def __post_init__(self) -> None:
        if self.default_role != ROLE_TECHNICIAN:
            raise ValueError(
                "Le rôle d'auto-provisionnement doit rester TECHNICIAN tant que le contrat Acumatica réel n'est pas validé."
            )


class IdentityProvisioningService:
    def __init__(
        self,
        repository: IdentityProvisioningRepositoryPort,
        policy: AutoProvisioningPolicy | None = None,
    ) -> None:
        self._repository = repository
        self._policy = policy or AutoProvisioningPolicy()

    def resolve_or_provision(
        self,
        *,
        issuer: str,
        subject: str,
        display_name: str,
        email: str | None,
        auth_mode: str = "oidc",
    ) -> AuthPrincipal | None:
        existing = self._repository.get_by_external_identity(issuer, subject)
        if existing is not None:
            # Never silently reactivate an account that an administrator disabled.
            if not existing.active:
                return None
            return IdentityService(self._repository).resolve(
                issuer=issuer,
                subject=subject,
                auth_mode=auth_mode,
            )

        if not self._policy.enabled:
            return None

        created = self._repository.upsert(
            issuer=issuer,
            subject=subject,
            display_name=display_name,
            email=email,
            roles=(self._policy.default_role,),
            active=True,
            employee_external_id=None,
        )
        return AuthPrincipal.from_roles(
            local_user_id=created.user_id,
            issuer=created.issuer,
            subject=created.subject,
            display_name=created.display_name,
            email=created.email,
            employee_external_id=created.employee_external_id,
            roles=created.roles,
            auth_mode=auth_mode,
        )
