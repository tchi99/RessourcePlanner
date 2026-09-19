"""Serve the built React V2 application against a fresh SQLite E2E fixture.

This process is intended for Playwright only. Authentication is resolved from
``X-E2E-Role`` so browser contexts can exercise real authorization middleware
without an external OIDC provider. No production authentication path is changed.
"""

from __future__ import annotations

import argparse
from datetime import time
from pathlib import Path
import sys

import uvicorn
from fastapi import Request


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.application.communications import (
    CommunicationTransportMessage,
    CommunicationTransportResult,
)
from app.application.security import (
    AuthPrincipal,
    ROLE_ADMIN,
    ROLE_COORDINATOR,
    ROLE_MANAGER,
    ROLE_PROJECT_MANAGER,
    ROLE_TECHNICIAN,
)
from app.infrastructure.sql import (
    Base,
    Competency,
    Project,
    Resource,
    ResourceAvailabilityRule,
    ResourceCompetency,
    SqlUserIdentityRepository,
    TaskCatalogEntry,
    create_session_factory,
    create_sql_engine,
)
from app.server import create_api_app
from app.server.dev_user_switcher import (
    DevUserSwitcherRuntime,
    dev_user_switcher_auth_resolver,
)
from app.server.frontend import attach_frontend


ROLE_IDENTITIES = {
    ROLE_ADMIN: ("Administrateur E2E", None),
    ROLE_PROJECT_MANAGER: ("Chargé E2E", None),
    ROLE_COORDINATOR: ("Coordonnateur E2E", None),
    ROLE_TECHNICIAN: ("Technicien Alice", "EMP-ALICE"),
}


class FakePlaywrightCommunicationTransport:
    """Capture draft creation locally; never contacts Microsoft 365."""

    def __init__(self) -> None:
        self.messages: tuple[CommunicationTransportMessage, ...] = ()

    def create_drafts(self, messages):
        self.messages = tuple(messages)
        return CommunicationTransportResult(
            provider="fake_playwright",
            created_count=len(self.messages),
        )


def _principal_for_request(request: Request) -> AuthPrincipal | None:
    role = str(request.headers.get("X-E2E-Role") or "").strip().upper()
    identity = ROLE_IDENTITIES.get(role)
    if identity is None:
        return None
    display_name, employee_external_id = identity
    return AuthPrincipal.from_roles(
        local_user_id=f"playwright-{role.lower()}",
        issuer="urn:resourceplanner:playwright",
        subject=f"playwright-{role.lower()}",
        display_name=display_name,
        email=None,
        employee_external_id=employee_external_id,
        roles=(role,),
        auth_mode="test",
    )


def _bootstrap_principal() -> AuthPrincipal:
    return AuthPrincipal.from_roles(
        local_user_id=None,
        issuer="urn:resourceplanner:local",
        subject="playwright-bootstrap",
        display_name="Administrateur bootstrap E2E",
        email=None,
        roles=(ROLE_ADMIN,),
        auth_mode="local",
    )


def _combined_auth_resolver(dev_resolver):
    def resolve(request: Request) -> AuthPrincipal | None:
        if str(request.headers.get("X-E2E-Anonymous") or "").strip():
            return None
        if str(request.headers.get("X-E2E-Role") or "").strip():
            return _principal_for_request(request)
        return dev_resolver(request)

    return resolve


def _seed(database_url: str) -> None:
    engine = create_sql_engine(database_url)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    address_domain = "example.test"
    try:
        with factory.begin() as session:
            session.add(
                Project(
                    id="P-251-ID",
                    number="P-251",
                    name="Projet Playwright V2",
                    client="Client E2E",
                    project_manager_name="Chargé E2E",
                    status="Actif",
                )
            )
            session.add(
                TaskCatalogEntry(
                    id="TASK-P251-210",
                    project_number="P-251",
                    task_code="210",
                    label="AUTOMATISATION E2E",
                    status="Actif",
                    active=True,
                    time_entry_enabled=True,
                    expenses_enabled=False,
                )
            )
            session.add_all(
                [
                    Competency(id="C-PLC", name="PLC", description="Programmation automate", active=True, sort_order=10),
                    Competency(id="C-SCADA", name="SCADA", description="Supervision industrielle", active=True, sort_order=20),
                    Competency(id="C-MES", name="MES", description="Systèmes d'exécution manufacturière", active=True, sort_order=30),
                ]
            )
            session.add_all(
                [
                    Resource(
                        id="R-ALICE",
                        external_id="EMP-ALICE",
                        name="Alice",
                        email=f"alice{chr(64)}{address_domain}",
                        resource_class="Programmation",
                        competencies="SCADA; MES",
                        active=True,
                        sort_order=10,
                    ),
                    Resource(
                        id="R-BOB",
                        external_id="EMP-BOB",
                        name="Bob",
                        email=f"bob{chr(64)}{address_domain}",
                        resource_class="Programmation",
                        competencies="PLC; SCADA",
                        active=True,
                        sort_order=20,
                    ),
                ]
            )
            session.flush()
            session.add_all(
                [
                    ResourceCompetency(resource_id="R-ALICE", competency_id="C-SCADA"),
                    ResourceCompetency(resource_id="R-ALICE", competency_id="C-MES"),
                    ResourceCompetency(resource_id="R-BOB", competency_id="C-PLC"),
                    ResourceCompetency(resource_id="R-BOB", competency_id="C-SCADA"),
                ]
            )
            for resource_id, suffix in (("R-ALICE", "ALICE"), ("R-BOB", "BOB")):
                session.add(
                    ResourceAvailabilityRule(
                        id=f"E2E-STD-{suffix}",
                        resource_id=resource_id,
                        availability_type="Horaire standard",
                        weekdays="Lun,Mar,Mer,Jeu,Ven,Sam,Dim",
                        start_time=time(8, 0),
                        end_time=time(16, 0),
                        active=True,
                    )
                )

            users = SqlUserIdentityRepository(session)
            for subject, display_name, role, employee_external_id in (
                ("admin", "Administrateur Démo", ROLE_ADMIN, None),
                ("coordinator", "Coordonnateur Démo", ROLE_COORDINATOR, None),
                ("project-manager", "Chargé de projet Démo", ROLE_PROJECT_MANAGER, None),
                ("manager", "Gestionnaire Démo", ROLE_MANAGER, None),
                ("technician-a", "Technicien Démo A", ROLE_TECHNICIAN, "EMP-ALICE"),
                ("technician-b", "Technicien Démo B", ROLE_TECHNICIAN, "EMP-BOB"),
            ):
                users.upsert(
                    issuer="urn:resourceplanner:e2e-dev",
                    subject=subject,
                    display_name=display_name,
                    email=None,
                    employee_external_id=employee_external_id,
                    roles=(role,),
                    active=True,
                )
    finally:
        engine.dispose()


def build_app(database_path: Path, frontend_dist: Path):
    database_path.parent.mkdir(parents=True, exist_ok=True)
    if database_path.exists():
        database_path.unlink()
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    _seed(database_url)
    transport = FakePlaywrightCommunicationTransport()
    dev_runtime = DevUserSwitcherRuntime(bootstrap_principal=_bootstrap_principal())
    dev_resolver = dev_user_switcher_auth_resolver(dev_runtime)
    app = create_api_app(
        database_url,
        auth_resolver=_combined_auth_resolver(dev_resolver),
        dev_user_switcher_runtime=dev_runtime,
        communication_transport=transport,
    )
    attach_frontend(app, frontend_dist, required=True)
    app.state.e2e_transport = transport
    return app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local RessourcePlanner Playwright fixture")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--database",
        type=Path,
        default=ROOT / ".e2e" / "resourceplanner-playwright.db",
    )
    parser.add_argument(
        "--frontend-dist",
        type=Path,
        default=ROOT / "frontend" / "dist",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app = build_app(args.database.resolve(), args.frontend_dist.resolve())
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
