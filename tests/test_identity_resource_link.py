from __future__ import annotations

import unittest

from app.application.errors import ApplicationConflictError, ApplicationNotFoundError
from app.application.identity_resource_link import IdentityResourceLinkService
from app.application.security import IdentityService, ROLE_TECHNICIAN
from app.infrastructure.sql import (
    Base,
    Resource,
    SqlIdentityResourceLinkRepository,
    SqlUserIdentityRepository,
    create_session_factory,
    create_sql_engine,
    transactional_session,
)


class IdentityResourceLinkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_sql_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.factory = create_session_factory(self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()

    def _user(self, subject: str) -> str:
        with transactional_session(self.factory) as session:
            record = SqlUserIdentityRepository(session).upsert(
                issuer="issuer-test",
                subject=subject,
                display_name=subject,
                email=None,
                roles=(ROLE_TECHNICIAN,),
            )
            return record.user_id

    def test_link_is_exposed_through_identity_principal(self) -> None:
        user_id = self._user("user-a")
        with transactional_session(self.factory) as session:
            session.add(Resource(id="RESOURCE-1", external_id="EMP-1", name="Ressource 1"))

        with transactional_session(self.factory) as session:
            linked = IdentityResourceLinkService(
                SqlIdentityResourceLinkRepository(session)
            ).link(user_id=user_id, employee_external_id="EMP-1")
            self.assertEqual(linked.employee_external_id, "EMP-1")

        with self.factory() as session:
            principal = IdentityService(SqlUserIdentityRepository(session)).resolve(
                issuer="issuer-test",
                subject="user-a",
            )
            assert principal is not None
            self.assertEqual(principal.employee_external_id, "EMP-1")
            self.assertEqual(principal.to_dict()["employee_external_id"], "EMP-1")

    def test_one_resource_cannot_be_linked_to_two_users(self) -> None:
        first_id = self._user("user-a")
        second_id = self._user("user-b")
        with transactional_session(self.factory) as session:
            session.add(Resource(id="RESOURCE-2", external_id="EMP-2", name="Ressource 2"))
        with transactional_session(self.factory) as session:
            service = IdentityResourceLinkService(SqlIdentityResourceLinkRepository(session))
            service.link(user_id=first_id, employee_external_id="EMP-2")
        with transactional_session(self.factory) as session:
            service = IdentityResourceLinkService(SqlIdentityResourceLinkRepository(session))
            with self.assertRaises(ApplicationConflictError) as raised:
                service.link(user_id=second_id, employee_external_id="EMP-2")
        self.assertEqual(raised.exception.code, "identity_resource_already_linked")

    def test_link_requires_a_synchronized_resource(self) -> None:
        user_id = self._user("user-c")
        with transactional_session(self.factory) as session:
            service = IdentityResourceLinkService(SqlIdentityResourceLinkRepository(session))
            with self.assertRaises(ApplicationNotFoundError) as raised:
                service.link(user_id=user_id, employee_external_id="EMP-MISSING")
        self.assertEqual(raised.exception.code, "identity_resource_resource_not_found")

    def test_unlink_is_explicit(self) -> None:
        user_id = self._user("user-d")
        with transactional_session(self.factory) as session:
            session.add(Resource(id="RESOURCE-4", external_id="EMP-4", name="Ressource 4"))
        with transactional_session(self.factory) as session:
            service = IdentityResourceLinkService(SqlIdentityResourceLinkRepository(session))
            service.link(user_id=user_id, employee_external_id="EMP-4")
            record = service.unlink(user_id=user_id)
            self.assertIsNone(record.employee_external_id)


if __name__ == "__main__":
    unittest.main()
