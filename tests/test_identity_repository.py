from __future__ import annotations

import unittest

from app.application.security import IdentityService, ROLE_ADMIN, ROLE_TECHNICIAN
from app.infrastructure.sql import Base, SqlUserIdentityRepository, create_session_factory, create_sql_engine


class IdentityRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_sql_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.factory = create_session_factory(self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_upsert_and_resolve_external_identity(self) -> None:
        email = "person" + chr(64) + "example.invalid"
        with self.factory.begin() as session:
            repository = SqlUserIdentityRepository(session)
            created = repository.upsert(
                issuer="https://issuer.example.invalid",
                subject="subject-1",
                display_name="Utilisateur test",
                email=email,
                roles=(ROLE_TECHNICIAN,),
            )
            principal = IdentityService(repository).resolve(
                issuer="https://issuer.example.invalid",
                subject="subject-1",
            )

        self.assertEqual(created.roles, (ROLE_TECHNICIAN,))
        self.assertIsNotNone(principal)
        assert principal is not None
        self.assertEqual(principal.local_user_id, created.user_id)
        self.assertEqual(principal.email, email)
        self.assertEqual(principal.roles, (ROLE_TECHNICIAN,))
        self.assertTrue(principal.has_permission("read"))

    def test_upsert_updates_roles_without_duplicate_identity(self) -> None:
        with self.factory.begin() as session:
            repository = SqlUserIdentityRepository(session)
            first = repository.upsert(
                issuer="issuer-a",
                subject="subject-a",
                display_name="Premier nom",
                email=None,
                roles=(ROLE_TECHNICIAN,),
            )
            second = repository.upsert(
                issuer="issuer-a",
                subject="subject-a",
                display_name="Nom modifié",
                email=None,
                roles=(ROLE_ADMIN,),
            )

        self.assertEqual(first.user_id, second.user_id)
        self.assertEqual(second.display_name, "Nom modifié")
        self.assertEqual(second.roles, (ROLE_ADMIN,))

    def test_inactive_user_does_not_resolve(self) -> None:
        with self.factory.begin() as session:
            repository = SqlUserIdentityRepository(session)
            repository.upsert(
                issuer="issuer-b",
                subject="subject-b",
                display_name="Inactive",
                email=None,
                roles=(ROLE_TECHNICIAN,),
                active=False,
            )
            principal = IdentityService(repository).resolve(
                issuer="issuer-b",
                subject="subject-b",
            )

        self.assertIsNone(principal)

    def test_invalid_role_is_rejected_before_persistence(self) -> None:
        with self.factory.begin() as session:
            repository = SqlUserIdentityRepository(session)
            with self.assertRaises(ValueError):
                repository.upsert(
                    issuer="issuer-c",
                    subject="subject-c",
                    display_name="Invalid role",
                    email=None,
                    roles=("UNKNOWN",),
                )


if __name__ == "__main__":
    unittest.main()
