from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from app.infrastructure.sql import Base, create_sql_engine
from app.server import create_api_app


class ServerResourceAdminRouteTests(unittest.TestCase):
    def _database(self, directory: str) -> str:
        path = Path(directory) / "resource-admin.db"
        url = f"sqlite:///{path.as_posix()}"
        engine = create_sql_engine(url)
        Base.metadata.create_all(engine)
        engine.dispose()
        return url

    def test_resource_profile_and_availability_lifecycle(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(self._database(directory))
            with TestClient(app) as client:
                test_email = "auto1" + chr(64) + "example.test"
                created = client.post(
                    "/api/v1/resources",
                    json={
                        "name": "Automatisation 1",
                        "email": test_email,
                        "resource_class": "Programmation",
                        "competencies": "PLC; SCADA",
                        "note": "Ressource de test",
                        "sort_order": 20,
                    },
                )
                self.assertEqual(created.status_code, 201, created.text)
                resource_id = created.json()["resource_id"]

                resources = client.get("/api/v1/resources?active_only=false")
                self.assertEqual(resources.status_code, 200, resources.text)
                self.assertEqual(len(resources.json()), 1)
                row = resources.json()[0]
                self.assertEqual(row["id"], resource_id)
                self.assertEqual(row["email"], test_email)
                self.assertEqual(row["resource_class"], "Programmation")
                self.assertEqual(row["competencies"], "PLC; SCADA")
                self.assertEqual(row["sort_order"], 20)

                duplicate = client.post(
                    "/api/v1/resources",
                    json={"name": "AUTOMATISATION 1"},
                )
                self.assertEqual(duplicate.status_code, 409, duplicate.text)
                self.assertEqual(
                    duplicate.json()["error"]["code"],
                    "resource_name_conflict",
                )

                updated = client.patch(
                    f"/api/v1/resources/{resource_id}",
                    json={
                        "competencies": "PLC; SCADA; MES",
                        "sort_order": 10,
                    },
                )
                self.assertEqual(updated.status_code, 200, updated.text)

                null_active = client.patch(
                    f"/api/v1/resources/{resource_id}",
                    json={"active": None},
                )
                self.assertEqual(null_active.status_code, 422, null_active.text)

                standard = client.post(
                    "/api/v1/availability-rules",
                    json={
                        "availability_type": "Horaire standard",
                        "resource_id": resource_id,
                        "start_date": "2026-01-01",
                        "end_date": "2027-12-31",
                        "weekdays": "Lun,Mar,Mer,Jeu,Ven",
                        "start_time": "07:00:00",
                        "end_time": "15:30:00",
                        "note": "Horaire régulier",
                    },
                )
                self.assertEqual(standard.status_code, 201, standard.text)
                standard_id = standard.json()["rule_id"]

                holiday = client.post(
                    "/api/v1/availability-rules",
                    json={
                        "availability_type": "Jour férié",
                        "start_date": "2026-12-25",
                        "end_date": "2026-12-25",
                        "note": "Noël",
                    },
                )
                self.assertEqual(holiday.status_code, 201, holiday.text)
                holiday_id = holiday.json()["rule_id"]

                missing_resource = client.post(
                    "/api/v1/availability-rules",
                    json={
                        "availability_type": "Vacances",
                        "start_date": "2026-10-01",
                        "end_date": "2026-10-02",
                    },
                )
                self.assertEqual(missing_resource.status_code, 422, missing_resource.text)
                self.assertEqual(
                    missing_resource.json()["error"]["code"],
                    "availability_resource_required",
                )

                invalid_weekday = client.post(
                    "/api/v1/availability-rules",
                    json={
                        "availability_type": "Horaire standard",
                        "resource_id": resource_id,
                        "weekdays": "Lundi,Mardi",
                        "start_time": "07:00:00",
                        "end_time": "15:30:00",
                    },
                )
                self.assertEqual(invalid_weekday.status_code, 422, invalid_weekday.text)
                self.assertEqual(
                    invalid_weekday.json()["error"]["code"],
                    "availability_weekdays_invalid",
                )

                scoped = client.get(
                    "/api/v1/availability-rules",
                    params={
                        "resource_id": resource_id,
                        "include_global": "true",
                        "active_only": "true",
                    },
                )
                self.assertEqual(scoped.status_code, 200, scoped.text)
                self.assertEqual(
                    {item["id"] for item in scoped.json()},
                    {standard_id, holiday_id},
                )
                standard_row = next(
                    item for item in scoped.json() if item["id"] == standard_id
                )
                self.assertEqual(standard_row["resource_name"], "Automatisation 1")
                self.assertEqual(standard_row["start_time"], "07:00:00")

                resource_only = client.get(
                    "/api/v1/availability-rules",
                    params={
                        "resource_id": resource_id,
                        "include_global": "false",
                    },
                )
                self.assertEqual(
                    [item["id"] for item in resource_only.json()],
                    [standard_id],
                )

                deactivated_rule = client.post(
                    f"/api/v1/availability-rules/{standard_id}/deactivate"
                )
                self.assertEqual(deactivated_rule.status_code, 200, deactivated_rule.text)

                active_rules = client.get(
                    "/api/v1/availability-rules",
                    params={"resource_id": resource_id, "include_global": "true"},
                )
                self.assertEqual(
                    [item["id"] for item in active_rules.json()],
                    [holiday_id],
                )
                all_rules = client.get(
                    "/api/v1/availability-rules",
                    params={
                        "resource_id": resource_id,
                        "include_global": "true",
                        "active_only": "false",
                    },
                )
                self.assertEqual(len(all_rules.json()), 2)
                inactive_standard = next(
                    item for item in all_rules.json() if item["id"] == standard_id
                )
                self.assertFalse(inactive_standard["active"])

                deactivated_resource = client.post(
                    f"/api/v1/resources/{resource_id}/deactivate"
                )
                self.assertEqual(
                    deactivated_resource.status_code,
                    200,
                    deactivated_resource.text,
                )
                self.assertEqual(client.get("/api/v1/resources").json(), [])
                inactive_resources = client.get(
                    "/api/v1/resources?active_only=false"
                ).json()
                self.assertEqual(len(inactive_resources), 1)
                self.assertFalse(inactive_resources[0]["active"])
                self.assertEqual(inactive_resources[0]["sort_order"], 10)

    def test_openapi_exposes_resource_admin_contracts(self) -> None:
        with TemporaryDirectory() as directory:
            app = create_api_app(self._database(directory))
            with TestClient(app) as client:
                schema = client.get("/openapi.json").json()

            paths = schema["paths"]
            self.assertIn("/api/v1/resources", paths)
            self.assertIn("/api/v1/resources/{resource_id}", paths)
            self.assertIn("/api/v1/availability-rules", paths)
            self.assertIn("/api/v1/availability-rules/{rule_id}", paths)
            self.assertIn("ResourceAvailabilityRuleReadModel", schema["components"]["schemas"])


if __name__ == "__main__":
    unittest.main()
