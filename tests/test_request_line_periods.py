from __future__ import annotations

from datetime import date
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from app.application.security import AuthPrincipal, ROLE_TECHNICIAN
from app.infrastructure.sql import Base, Project, Resource, create_session_factory, create_sql_engine
from app.server import create_api_app
from app.server.security import static_auth_resolver
from tests.http_test_auth import TEST_ADMIN_AUTH_RESOLVER


D1 = date(2026, 9, 21)
D2 = date(2026, 9, 22)

create_api_app = partial(create_api_app, auth_resolver=TEST_ADMIN_AUTH_RESOLVER)


class RequestLinePeriodApiTests(unittest.TestCase):
    @staticmethod
    def _database(directory: str) -> str:
        path = Path(directory) / "line-periods.db"
        url = f"sqlite:///{path.as_posix()}"
        engine = create_sql_engine(url)
        Base.metadata.create_all(engine)
        factory = create_session_factory(engine)
        with factory.begin() as session:
            session.add(Project(id="P1", number="P-1", name="Projet lignes"))
            session.add_all(
                [
                    Resource(id="R1", name="Alice", active=True),
                    Resource(id="R2", name="Bob", active=True),
                ]
            )
        engine.dispose()
        return url

    @staticmethod
    def _create_multiline(client: TestClient) -> tuple[str, list[str]]:
        created = client.post(
            "/api/v1/demands",
            json={
                "project_number": "P-1",
                "lines": [
                    {
                        "required_resource_class": "Automatisation",
                        "desired_start": D1.isoformat(),
                        "desired_active_days": 1,
                    },
                    {
                        "required_resource_class": "Électricité",
                        "desired_start": D2.isoformat(),
                        "desired_active_days": 1,
                    },
                ],
            },
        )
        assert created.status_code == 201, created.text
        number = created.json()["demand_number"]
        demand = client.get(f"/api/v1/demands/{number}")
        assert demand.status_code == 200, demand.text
        line_ids = [
            row["line_id"]
            for row in demand.json()["lines"]
            if row["active"]
        ]
        assert len(line_ids) == 2
        return number, line_ids

    @staticmethod
    def _alternatives(prefix: str) -> dict:
        return {
            "periods": [
                {
                    "period_id": f"{prefix}-A",
                    "start_date": D1.isoformat(),
                    "end_date": D1.isoformat(),
                    "hours": 8,
                    "kind": "ALTERNATIVE",
                    "alternative_group": "VISITE",
                    "desired_active_days": 1,
                },
                {
                    "period_id": f"{prefix}-B",
                    "start_date": D2.isoformat(),
                    "end_date": D2.isoformat(),
                    "hours": 8,
                    "kind": "ALTERNATIVE",
                    "alternative_group": "VISITE",
                    "desired_active_days": 1,
                },
            ]
        }

    def test_same_alternative_group_is_independent_on_two_lines(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(self._database(directory), actor_name="coord")
            with TestClient(app, raise_server_exceptions=False) as client:
                number, (line_a, line_b) = self._create_multiline(client)

                first = client.put(
                    f"/api/v1/demands/{number}/lines/{line_a}/periods",
                    json=self._alternatives("L1"),
                )
                second = client.put(
                    f"/api/v1/demands/{number}/lines/{line_b}/periods",
                    json=self._alternatives("L2"),
                )
                self.assertEqual(first.status_code, 200, first.text)
                self.assertEqual(second.status_code, 200, second.text)

                legacy = client.get(f"/api/v1/demands/{number}/periods")
                self.assertEqual(legacy.status_code, 409, legacy.text)
                self.assertEqual(
                    legacy.json()["error"]["code"],
                    "demand_line_period_scope_required",
                )

                line_a_periods = client.get(
                    f"/api/v1/demands/{number}/lines/{line_a}/periods"
                )
                line_b_periods = client.get(
                    f"/api/v1/demands/{number}/lines/{line_b}/periods"
                )
                self.assertEqual(line_a_periods.status_code, 200, line_a_periods.text)
                self.assertEqual(line_b_periods.status_code, 200, line_b_periods.text)
                self.assertEqual(
                    [row["period_id"] for row in line_a_periods.json()],
                    ["L1-A", "L1-B"],
                )
                self.assertEqual(
                    [row["period_id"] for row in line_b_periods.json()],
                    ["L2-A", "L2-B"],
                )
                self.assertTrue(
                    all(row["request_line_id"] == line_a for row in line_a_periods.json())
                )
                self.assertTrue(
                    all(row["request_line_id"] == line_b for row in line_b_periods.json())
                )

                selected_a = client.put(
                    f"/api/v1/demands/{number}/lines/{line_a}/alternative-groups/VISITE/selection",
                    json={"period_id": "L1-A"},
                )
                selected_b = client.put(
                    f"/api/v1/demands/{number}/lines/{line_b}/alternative-groups/VISITE/selection",
                    json={"period_id": "L2-B"},
                )
                self.assertEqual(selected_a.status_code, 200, selected_a.text)
                self.assertEqual(selected_b.status_code, 200, selected_b.text)

                selected_a_rows = client.get(
                    f"/api/v1/demands/{number}/lines/{line_a}/periods"
                ).json()
                selected_b_rows = client.get(
                    f"/api/v1/demands/{number}/lines/{line_b}/periods"
                ).json()
                self.assertEqual(
                    [row["period_id"] for row in selected_a_rows if row["selected"]],
                    ["L1-A"],
                )
                self.assertEqual(
                    [row["period_id"] for row in selected_b_rows if row["selected"]],
                    ["L2-B"],
                )

    def test_replace_is_line_scoped_and_validates_slot_semantics_and_ownership(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(self._database(directory), actor_name="coord")
            with TestClient(app, raise_server_exceptions=False) as client:
                number, (line_a, line_b) = self._create_multiline(client)
                self.assertEqual(
                    client.put(
                        f"/api/v1/demands/{number}/lines/{line_a}/periods",
                        json=self._alternatives("A"),
                    ).status_code,
                    200,
                )
                self.assertEqual(
                    client.put(
                        f"/api/v1/demands/{number}/lines/{line_b}/periods",
                        json=self._alternatives("B"),
                    ).status_code,
                    200,
                )

                changed = self._alternatives("A")
                changed["periods"][0]["desired_active_days"] = 2
                changed["periods"][0]["end_date"] = D2.isoformat()
                replaced = client.put(
                    f"/api/v1/demands/{number}/lines/{line_a}/periods",
                    json=changed,
                )
                self.assertEqual(replaced.status_code, 200, replaced.text)
                a_rows = client.get(
                    f"/api/v1/demands/{number}/lines/{line_a}/periods"
                ).json()
                b_rows = client.get(
                    f"/api/v1/demands/{number}/lines/{line_b}/periods"
                ).json()
                self.assertEqual(a_rows[0]["desired_active_days"], 2)
                self.assertEqual(
                    [row["period_id"] for row in b_rows],
                    ["B-A", "B-B"],
                )

                invalid_count = self._alternatives("COUNT")
                invalid_count["periods"][0]["resource_count"] = 2
                rejected = client.put(
                    f"/api/v1/demands/{number}/lines/{line_a}/periods",
                    json=invalid_count,
                )
                self.assertEqual(rejected.status_code, 422, rejected.text)
                self.assertEqual(
                    rejected.json()["error"]["code"],
                    "demand_line_period_resource_count_invalid",
                )

                other_created = client.post(
                    "/api/v1/demands",
                    json={
                        "project_number": "P-1",
                        "lines": [
                            {
                                "desired_start": D1.isoformat(),
                                "desired_active_days": 1,
                            }
                        ],
                    },
                )
                other_number = other_created.json()["demand_number"]
                foreign_line = client.get(
                    f"/api/v1/demands/{other_number}"
                ).json()["lines"][0]["line_id"]
                foreign = client.put(
                    f"/api/v1/demands/{number}/lines/{foreign_line}/periods",
                    json=self._alternatives("FOREIGN"),
                )
                self.assertEqual(foreign.status_code, 404, foreign.text)
                self.assertEqual(
                    foreign.json()["error"]["code"],
                    "demand_line_not_found",
                )

    def test_line_period_routes_keep_existing_rbac(self) -> None:
        with TemporaryDirectory() as directory:
            database_url = self._database(directory)
            admin_app = create_api_app(database_url, actor_name="coord")
            with TestClient(admin_app, raise_server_exceptions=False) as admin:
                number, (line_a, _line_b) = self._create_multiline(admin)

            technician = AuthPrincipal.from_roles(
                local_user_id="tech",
                issuer="urn:test",
                subject="tech",
                display_name="Technicien",
                email=None,
                roles=(ROLE_TECHNICIAN,),
                auth_mode="test",
            )
            read_only_app = create_api_app(
                database_url,
                auth_resolver=static_auth_resolver(technician),
            )
            with TestClient(read_only_app, raise_server_exceptions=False) as client:
                read = client.get(
                    f"/api/v1/demands/{number}/lines/{line_a}/periods"
                )
                write = client.put(
                    f"/api/v1/demands/{number}/lines/{line_a}/periods",
                    json=self._alternatives("RBAC"),
                )

            self.assertEqual(read.status_code, 200, read.text)
            self.assertEqual(write.status_code, 403, write.text)
            self.assertEqual(write.json()["error"]["code"], "permission_denied")


if __name__ == "__main__":
    unittest.main()
