from __future__ import annotations

import unittest

from app.application.identity_provisioning import (
    AutoProvisioningPolicy,
    IdentityProvisioningService,
)
from app.application.security import ROLE_ADMIN, ROLE_TECHNICIAN
from app.infrastructure.sql import Base, SqlUserIdentityRepository, create_session_factory, create_sql_engine


class IdentityProvisioningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_sql_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.factory = create_session_factory(self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_unknown_identity_is_denied_by_default(self) -> None:
        with self.factory.begin() as session:
            repository = SqlUserIdentityRepository(session)
            principal = IdentityProvisioningService(repository).resolve_or_provision(
                issuer="issuer-test",
                subject="new-user",
                display_name="Nouvel utilisateur",
                email=None,
            )
            self.assertIsNone(principal)
            self.assertIsNone(
                repository.get_by_external_identity("issuer-test", "new-user")
            )

    def test_enabled_policy_creates_only_read_only_technician(self) -> None:
        with self.factory.begin() as session:
            repository = SqlUserIdentityRepository(session)
            principal = IdentityProvisioningService(
                repository,
                AutoProvisioningPolicy(enabled=True),
            ).resolve_or_provision(
                issuer="issuer-test",
                subject="new-user",
                display_name="Nouvel utilisateur",
                email=None,
            )
            assert principal is not None
            self.assertEqual(principal.roles, (ROLE_TECHNICIAN,))
            self.assertEqual(principal.permissions, ("read",))
            self.assertIsNone(principal.employee_external_id)

    def test_disabled_existing_user_is_never_reactivated(self) -> None:
        with self.factory.begin() as session:
            repository = SqlUserIdentityRepository(session)
            repository.upsert(
                issuer="issuer-test",
                subject="disabled-user",
                display_name="Utilisateur désactivé",
                email=None,
                roles=(ROLE_TECHNICIAN,),
                active=False,
            )
            principal = IdentityProvisioningService(
                repository,
                AutoProvisioningPolicy(enabled=True),
            ).resolve_or_provision(
                issuer="issuer-test",
                subject="disabled-user",
                display_name="Nom OIDC modifié",
                email=None,
            )
            self.assertIsNone(principal)
            record = repository.get_by_external_identity("issuer-test", "disabled-user")
            assert record is not None
            self.assertFalse(record.active)
            self.assertEqual(record.display_name, "Utilisateur désactivé")

    def test_privileged_default_role_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            AutoProvisioningPolicy(enabled=True, default_role=ROLE_ADMIN)


if __name__ == "__main__":
    unittest.main()
