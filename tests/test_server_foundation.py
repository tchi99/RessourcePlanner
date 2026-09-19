from __future__ import annotations

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select

from app.application import (
    ApplicationFacade,
    ApplicationValidationError,
    DemandCreateCommand,
)
from app.infrastructure.sql import (
    Base,
    Project,
    WorkforceRequest,
    create_session_factory,
    create_sql_engine,
    transactional_session,
)
from app.server import build_sql_facade, create_api_app
from app.server.security import static_auth_resolver


class ServerFoundationTests(unittest.TestCase):
    def test_api_factory_requires_explicit_auth_resolver(self) -> None:
        with self.assertRaises(ValueError) as caught:
            create_api_app("sqlite+pysqlite:///:memory:")
        self.assertIn("auth_resolver explicite", str(caught.exception))

    def test_api_docs_can_be_disabled_explicitly(self) -> None:
        app = create_api_app(
            "sqlite+pysqlite:///:memory:",
            auth_resolver=static_auth_resolver(None),
            api_docs_enabled=False,
        )
        with TestClient(app) as client:
            self.assertEqual(client.get("/docs").status_code, 404)
            self.assertEqual(client.get("/redoc").status_code, 404)
            self.assertEqual(client.get("/openapi.json").status_code, 404)

    def test_sql_composition_builds_real_application_facade(self) -> None:
        engine = create_sql_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        factory = create_session_factory(engine)
        try:
            with transactional_session(factory) as session:
                session.add(Project(id="P1", number="P-1", name="Projet API"))

            with transactional_session(factory) as session:
                facade = build_sql_facade(session, actor_name="Jean")
                result = facade.create_demand(
                    DemandCreateCommand(
                        project_number="P-1",
                        desired_start=date(2026, 8, 26),
                        description="Test API",
                    )
                )
                self.assertTrue(result.demand_number.startswith("DMO-"))
                self.assertEqual(result.status, "Brouillon")

            with factory() as session:
                request = session.scalar(select(WorkforceRequest))
                self.assertIsNotNone(request)
                assert request is not None
                self.assertEqual(request.requester_name, "Jean")
                self.assertEqual(request.description, "Test API")
        finally:
            engine.dispose()

    def test_health_does_not_run_schema_migrations(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "health.db"
            database_url = f"sqlite:///{database_path.as_posix()}"
            app = create_api_app(database_url, auth_resolver=static_auth_resolver(None))

            with TestClient(app) as client:
                response = client.get("/health")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"status": "ok", "api": "v1"})

            engine = create_sql_engine(database_url)
            try:
                self.assertEqual(inspect(engine).get_table_names(), [])
            finally:
                engine.dispose()

    def test_request_transaction_rolls_back_when_endpoint_fails(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "rollback.db"
            database_url = f"sqlite:///{database_path.as_posix()}"
            setup_engine = create_sql_engine(database_url)
            Base.metadata.create_all(setup_engine)
            setup_factory = create_session_factory(setup_engine)
            with transactional_session(setup_factory) as session:
                session.add(Project(id="P1", number="P-1", name="Projet API"))
            setup_engine.dispose()

            app = create_api_app(
                database_url,
                actor_name="Jean",
                auth_resolver=static_auth_resolver(None),
            )
            facade_dependency = app.state.facade_dependency

            @app.post("/_test/rollback")
            def fail_after_write(
                facade: ApplicationFacade = Depends(facade_dependency),
            ) -> None:
                facade.create_demand(
                    DemandCreateCommand(
                        project_number="P-1",
                        desired_start=date(2026, 8, 26),
                    )
                )
                raise RuntimeError("force rollback")

            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.post("/_test/rollback")
            self.assertEqual(response.status_code, 500)
            self.assertEqual(response.json()["error"]["code"], "internal_error")

            verify_engine = create_sql_engine(database_url)
            verify_factory = create_session_factory(verify_engine)
            try:
                with verify_factory() as session:
                    count = session.scalar(
                        select(func.count()).select_from(WorkforceRequest)
                    )
                    self.assertEqual(int(count or 0), 0)
            finally:
                verify_engine.dispose()

    def test_application_error_is_translated_to_stable_http_contract(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "errors.db"
            app = create_api_app(
                f"sqlite:///{database_path.as_posix()}",
                auth_resolver=static_auth_resolver(None),
            )

            @app.get("/_test/validation")
            def validation_failure() -> None:
                raise ApplicationValidationError(
                    "Valeur invalide",
                    code="sample_invalid",
                    context={"field": "sample"},
                )

            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.get("/_test/validation")

            self.assertEqual(response.status_code, 422)
            self.assertEqual(
                response.json(),
                {
                    "error": {
                        "code": "sample_invalid",
                        "message": "Valeur invalide",
                        "context": {"field": "sample"},
                    }
                },
            )


if __name__ == "__main__":
    unittest.main()
