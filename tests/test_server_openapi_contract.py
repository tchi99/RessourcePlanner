from __future__ import annotations

import json
import unittest

from fastapi.testclient import TestClient

from app.server import create_api_app
from tests.http_test_auth import TEST_ADMIN_AUTH_RESOLVER


class ServerOpenApiContractTests(unittest.TestCase):
    """Inspect the canonical API schema once for structure-only assertions."""

    @classmethod
    def setUpClass(cls) -> None:
        app = create_api_app(
            "sqlite+pysqlite:///:memory:",
            auth_resolver=TEST_ADMIN_AUTH_RESOLVER,
        )
        with TestClient(app) as client:
            response = client.get("/openapi.json")

        cls.status_code = response.status_code
        cls.schema = response.json()
        cls.serialized_schema = json.dumps(cls.schema, ensure_ascii=False)

    def test_work_package_read_model_is_exposed(self) -> None:
        components = self.schema.get("components", {}).get("schemas", {})
        self.assertIn("WorkPackageReadModel", components)
        self.assertIn("/api/v1/work-packages", self.schema["paths"])

    def test_typed_read_models_are_exposed(self) -> None:
        components = self.schema.get("components", {}).get("schemas", {})
        for expected in (
            "ProjectReadModel",
            "ResourceReadModel",
            "DemandReadModel",
            "SegmentReadModel",
            "ShiftReadModel",
            "PlanningSnapshotReadModel",
        ):
            self.assertIn(expected, components)

    def test_work_package_create_patch_and_idempotency_header_are_exposed(self) -> None:
        self.assertIn("post", self.schema["paths"]["/api/v1/work-packages"])
        self.assertIn("/api/v1/work-packages/{reference}", self.schema["paths"])
        parameters = self.schema["paths"]["/api/v1/work-packages"]["post"].get(
            "parameters", []
        )
        self.assertTrue(
            any(
                parameter.get("name") == "Idempotency-Key"
                and parameter.get("in") == "header"
                for parameter in parameters
            )
        )

    def test_canonical_contract_does_not_expose_excel_column_names(self) -> None:
        self.assertEqual(self.status_code, 200)
        self.assertIn("project_number", self.serialized_schema)
        self.assertIn("desired_start", self.serialized_schema)
        self.assertIn("source_effort_id", self.serialized_schema)
        for legacy in (
            "NumeroProjet",
            "DateDebutSouhaitee",
            "HeuresPrevues",
            "IDSegment",
            "IDAllocation",
            "source_effort_row",
            "SourceEffortRow",
        ):
            self.assertNotIn(legacy, self.serialized_schema)

    def test_creation_endpoints_expose_optional_idempotency_header(self) -> None:
        operations = (
            ("/api/v1/demands", "post"),
            ("/api/v1/segments", "post"),
            ("/api/v1/segments/{segment_id}/allocations", "post"),
            ("/api/v1/quick-shifts", "post"),
        )
        for path, method in operations:
            parameters = self.schema["paths"][path][method].get("parameters", [])
            idempotency = [
                parameter
                for parameter in parameters
                if parameter.get("name") == "Idempotency-Key"
                and parameter.get("in") == "header"
            ]
            self.assertEqual(len(idempotency), 1, f"Missing header on {method} {path}")
            self.assertFalse(idempotency[0].get("required", False))

    def test_resource_admin_contracts_are_exposed(self) -> None:
        paths = self.schema["paths"]
        self.assertIn("/api/v1/resources", paths)
        self.assertIn("/api/v1/resources/{resource_id}", paths)
        self.assertIn("/api/v1/availability-rules", paths)
        self.assertIn("/api/v1/availability-rules/{rule_id}", paths)
        self.assertIn(
            "ResourceAvailabilityRuleReadModel",
            self.schema["components"]["schemas"],
        )


if __name__ == "__main__":
    unittest.main()
