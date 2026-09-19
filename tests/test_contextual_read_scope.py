from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from app.application.security import (
    ROLE_PROJECT_MANAGER,
    ROLE_TECHNICIAN,
    AuthPrincipal,
)
from app.infrastructure.sql import (
    Base,
    Project,
    Resource,
    ResourceRequirement,
    SqlDemandRepository,
    WorkPackage,
    create_session_factory,
    create_sql_engine,
)
from app.server import create_api_app
from app.server.security import static_auth_resolver


DAY = date(2026, 9, 21)


class ContextualReadScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        database = Path(self.temp.name) / "scope.db"
        self.database_url = f"sqlite+pysqlite:///{database.as_posix()}"
        engine = create_sql_engine(self.database_url)
        Base.metadata.create_all(engine)
        factory = create_session_factory(engine)
        try:
            with factory.begin() as session:
                session.add_all(
                    [
                        Project(
                            id="P-MANAGED",
                            number="P-100",
                            name="Projet géré",
                            project_manager_external_id="EMP-MULTI",
                            project_manager_name="Gestionnaire multi",
                            status="Actif",
                        ),
                        Project(
                            id="P-PARTICIPATING",
                            number="P-200",
                            name="Projet participé",
                            status="Actif",
                        ),
                        Project(
                            id="P-PM-ONLY",
                            number="P-300",
                            name="Projet CP sans ressource",
                            project_manager_external_id="EMP-PM-ONLY",
                            project_manager_name="Gestionnaire sans ressource",
                            status="Actif",
                        ),
                        Project(
                            id="P-OTHER",
                            number="P-900",
                            name="Projet global seulement",
                            status="Actif",
                        ),
                    ]
                )
                session.add(
                    Resource(
                        id="R-MULTI",
                        external_id="EMP-MULTI",
                        name="Ressource multi-rôle",
                        active=True,
                        sort_order=10,
                    )
                )
                session.flush()
                session.add(
                    ResourceRequirement(
                        id="REQ-PARTICIPATING",
                        project_id="P-PARTICIPATING",
                        assigned_resource_id="R-MULTI",
                        start_date=DAY,
                        end_date=DAY,
                        planned_hours=Decimal("8"),
                        status="Planifié",
                        origin="AD_HOC",
                    )
                )
                session.add_all(
                    [
                        WorkPackage(
                            id="WP-MANAGED",
                            project_id="P-MANAGED",
                            code="MGT",
                            name="WP géré",
                            status="planned",
                        ),
                        WorkPackage(
                            id="WP-PARTICIPATING",
                            project_id="P-PARTICIPATING",
                            code="PART",
                            name="WP participé",
                            status="planned",
                        ),
                        WorkPackage(
                            id="WP-PM-ONLY",
                            project_id="P-PM-ONLY",
                            code="PM",
                            name="WP CP seul",
                            status="planned",
                        ),
                        WorkPackage(
                            id="WP-OTHER",
                            project_id="P-OTHER",
                            code="OTH",
                            name="WP global",
                            status="planned",
                        ),
                    ]
                )
                demands = SqlDemandRepository(session, actor_name="test")
                for project_number in ("P-100", "P-200", "P-300", "P-900"):
                    demands.create(
                        {
                            "NumeroProjet": project_number,
                            "DateDebutSouhaitee": DAY,
                            "DateFinSouhaitee": DAY,
                            "Description": f"Demande {project_number}",
                            "NombreRessources": 1,
                        }
                    )
        finally:
            engine.dispose()

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def principal(
        employee_external_id: str | None,
        roles: tuple[str, ...],
    ) -> AuthPrincipal:
        return AuthPrincipal.from_roles(
            local_user_id="U-SCOPE",
            issuer="urn:test",
            subject="scope-user",
            display_name="Utilisateur scope",
            email=None,
            employee_external_id=employee_external_id,
            roles=roles,
            auth_mode="local",
        )

    def client_for(self, principal: AuthPrincipal) -> TestClient:
        return TestClient(
            create_api_app(
                self.database_url,
                auth_resolver=static_auth_resolver(principal),
            )
        )

    def test_mine_scope_unions_managed_and_participating_projects(self) -> None:
        principal = self.principal(
            "EMP-MULTI",
            (ROLE_PROJECT_MANAGER, ROLE_TECHNICIAN),
        )
        with self.client_for(principal) as client:
            projects = client.get("/api/v1/projects", params={"scope": "mine"})
            demands = client.get("/api/v1/demands", params={"scope": "mine"})
            packages = client.get("/api/v1/work-packages", params={"scope": "mine"})

        self.assertEqual(projects.status_code, 200)
        self.assertEqual(
            {row["number"] for row in projects.json()},
            {"P-100", "P-200"},
        )
        self.assertEqual(
            {row["project_number"] for row in demands.json()},
            {"P-100", "P-200"},
        )
        self.assertEqual(
            {row["project_number"] for row in packages.json()},
            {"P-100", "P-200"},
        )

    def test_global_scope_preserves_authorized_global_reads(self) -> None:
        principal = self.principal(
            "EMP-MULTI",
            (ROLE_PROJECT_MANAGER, ROLE_TECHNICIAN),
        )
        with self.client_for(principal) as client:
            explicit_global = client.get(
                "/api/v1/projects",
                params={"scope": "global"},
            )
            default_global = client.get("/api/v1/projects")

        expected = {"P-100", "P-200", "P-300", "P-900"}
        self.assertEqual(
            {row["number"] for row in explicit_global.json()},
            expected,
        )
        self.assertEqual(
            {row["number"] for row in default_global.json()},
            expected,
        )

    def test_project_manager_without_resource_keeps_managed_reads(self) -> None:
        principal = self.principal("EMP-PM-ONLY", (ROLE_PROJECT_MANAGER,))
        with self.client_for(principal) as client:
            projects = client.get("/api/v1/projects", params={"scope": "mine"})
            demands = client.get("/api/v1/demands", params={"scope": "mine"})
            packages = client.get("/api/v1/work-packages", params={"scope": "mine"})

        self.assertEqual(
            [row["number"] for row in projects.json()],
            ["P-300"],
        )
        self.assertEqual(
            [row["project_number"] for row in demands.json()],
            ["P-300"],
        )
        self.assertEqual(
            [row["project_number"] for row in packages.json()],
            ["P-300"],
        )

    def test_empty_mine_scope_never_falls_back_to_global(self) -> None:
        principal = self.principal("EMP-UNKNOWN", (ROLE_TECHNICIAN,))
        with self.client_for(principal) as client:
            projects = client.get("/api/v1/projects", params={"scope": "mine"})
            demands = client.get("/api/v1/demands", params={"scope": "mine"})
            packages = client.get("/api/v1/work-packages", params={"scope": "mine"})

        self.assertEqual(projects.json(), [])
        self.assertEqual(demands.json(), [])
        self.assertEqual(packages.json(), [])

    def test_project_number_and_mine_scope_are_intersected(self) -> None:
        principal = self.principal(
            "EMP-MULTI",
            (ROLE_PROJECT_MANAGER, ROLE_TECHNICIAN),
        )
        with self.client_for(principal) as client:
            allowed = client.get(
                "/api/v1/work-packages",
                params={"scope": "mine", "project_number": "P-100"},
            )
            outside = client.get(
                "/api/v1/work-packages",
                params={"scope": "mine", "project_number": "P-900"},
            )

        self.assertEqual(
            [row["project_number"] for row in allowed.json()],
            ["P-100"],
        )
        self.assertEqual(outside.json(), [])

    def test_invalid_scope_is_rejected_before_query_execution(self) -> None:
        principal = self.principal("EMP-MULTI", (ROLE_PROJECT_MANAGER,))
        with self.client_for(principal) as client:
            response = client.get(
                "/api/v1/projects",
                params={"scope": "everything"},
            )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["error"]["code"],
            "request_validation_error",
        )


if __name__ == "__main__":
    unittest.main()
