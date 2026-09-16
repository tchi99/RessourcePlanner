from __future__ import annotations

import unittest

from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.infrastructure.sql import Base, create_sql_engine


class AcumaticaIdentitySchemaTests(unittest.TestCase):
    def test_employee_link_column_is_nullable_and_filtered_indexes_exist(self) -> None:
        users = Base.metadata.tables["app_users"]
        resources = Base.metadata.tables["resources"]
        self.assertTrue(users.c.employee_external_id.nullable)
        self.assertTrue(resources.c.external_id.nullable)
        self.assertIn(
            "ux_app_users_employee_external_id_not_null",
            {index.name for index in users.indexes},
        )
        self.assertIn(
            "ux_resources_external_id_not_null",
            {index.name for index in resources.indexes},
        )

    def test_multiple_nulls_are_allowed_but_duplicate_external_ids_are_rejected(self) -> None:
        engine = create_sql_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        resources = Base.metadata.tables["resources"]
        users = Base.metadata.tables["app_users"]
        with engine.begin() as connection:
            connection.execute(resources.insert().values(id="R1", name="Ressource A"))
            connection.execute(resources.insert().values(id="R2", name="Ressource B"))
            connection.execute(
                resources.insert().values(id="R3", name="Ressource C", external_id="EMP-1")
            )
            connection.execute(
                users.insert().values(
                    id="U1",
                    issuer="issuer",
                    subject="subject-1",
                    display_name="Utilisateur 1",
                    roles_json='["TECHNICIAN"]',
                )
            )
            connection.execute(
                users.insert().values(
                    id="U2",
                    issuer="issuer",
                    subject="subject-2",
                    display_name="Utilisateur 2",
                    roles_json='["TECHNICIAN"]',
                )
            )

        with self.assertRaises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    resources.insert().values(
                        id="R4",
                        name="Ressource D",
                        external_id="EMP-1",
                    )
                )

        with engine.begin() as connection:
            connection.execute(
                users.update().where(users.c.id == "U1").values(employee_external_id="EMP-2")
            )
        with self.assertRaises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    users.update().where(users.c.id == "U2").values(employee_external_id="EMP-2")
                )
        engine.dispose()

    def test_sqlite_runtime_contains_filtered_unique_indexes(self) -> None:
        engine = create_sql_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        inspector = inspect(engine)
        resource_indexes = {item["name"] for item in inspector.get_indexes("resources")}
        user_indexes = {item["name"] for item in inspector.get_indexes("app_users")}
        self.assertIn("ux_resources_external_id_not_null", resource_indexes)
        self.assertIn("ux_app_users_employee_external_id_not_null", user_indexes)
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
