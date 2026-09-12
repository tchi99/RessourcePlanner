from __future__ import annotations

import unittest

import httpx

from app.application import ApplicationOperationError
from app.infrastructure.acumatica import AcumaticaProjectSource, AcumaticaProjectSourceSettings


class AcumaticaProjectSourceTests(unittest.TestCase):
    def test_reads_paginated_contract_rest_projects_and_never_exposes_token(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            self.assertEqual(request.headers.get("Authorization"), "Bearer secret-token")
            skip = request.url.params.get("$skip")
            if skip == "0":
                payload = [
                    {
                        "id": "ERP-1",
                        "ProjectID": {"value": "P-100"},
                        "Description": {"value": "Projet 100"},
                        "Customer": {"value": "Client A"},
                        "ProjectManager": {"value": "Alice"},
                        "Status": {"value": "Active"},
                    },
                    {
                        "id": "ERP-2",
                        "ProjectID": {"value": "P-200"},
                        "Description": {"value": "Projet 200"},
                        "Customer": {"value": "Client B"},
                        "ProjectManager": {"value": "Bob"},
                        "Status": {"value": "Completed"},
                    },
                ]
            else:
                payload = [
                    {
                        "id": "ERP-3",
                        "ProjectID": {"value": "P-300"},
                        "Description": {"value": "Projet 300"},
                        "Customer": {"value": None},
                        "ProjectManager": {"value": None},
                        "Status": {"value": "Inactive"},
                    }
                ]
            return httpx.Response(200, json=payload)

        settings = AcumaticaProjectSourceSettings(
            base_url="https://erp.example.test/Instance",
            access_token="secret-token",
            endpoint="Default",
            version="25.200.001",
            entity="Project",
            page_size=2,
        )
        source = AcumaticaProjectSource(settings, transport=httpx.MockTransport(handler))

        rows = source.list_projects()

        self.assertEqual([row.number for row in rows], ["P-100", "P-200", "P-300"])
        self.assertEqual(rows[0].client, "Client A")
        self.assertEqual(rows[1].project_manager_name, "Bob")
        self.assertEqual(rows[2].status, "Inactive")
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0].url.path, "/Instance/entity/Default/25.200.001/Project")
        self.assertEqual(requests[0].url.params.get("$top"), "2")
        self.assertEqual(requests[0].url.params.get("$skip"), "0")
        self.assertIn("ProjectID", requests[0].url.params.get("$select", ""))
        self.assertNotIn("secret-token", repr(settings))
        self.assertNotIn("secret-token", str(settings.safe_summary()))

    def test_field_mapping_is_configurable(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "ERP-X",
                        "Nbr": {"value": "X-1"},
                        "Label": {"value": "Projet personnalisé"},
                        "Account": {"value": "Client X"},
                        "Owner": {"value": "Caroline"},
                        "State": {"value": "Open"},
                    }
                ],
            )

        settings = AcumaticaProjectSourceSettings(
            base_url="https://erp.example.test",
            access_token="token",
            version="custom-v1",
            entity="CustomProject",
            number_field="Nbr",
            name_field="Label",
            client_field="Account",
            project_manager_field="Owner",
            status_field="State",
        )
        row = AcumaticaProjectSource(
            settings,
            transport=httpx.MockTransport(handler),
        ).list_projects()[0]
        self.assertEqual(row.number, "X-1")
        self.assertEqual(row.name, "Projet personnalisé")
        self.assertEqual(row.client, "Client X")
        self.assertEqual(row.project_manager_name, "Caroline")
        self.assertEqual(row.status, "Open")

    def test_http_failure_is_translated_without_leaking_response_body(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, text="sensitive upstream response")

        source = AcumaticaProjectSource(
            AcumaticaProjectSourceSettings(
                base_url="https://erp.example.test",
                access_token="secret-token",
                version="25.200.001",
            ),
            transport=httpx.MockTransport(handler),
        )
        with self.assertRaises(ApplicationOperationError) as raised:
            source.list_projects()
        self.assertEqual(raised.exception.code, "acumatica_project_read_failed")
        self.assertNotIn("sensitive", raised.exception.message)
        self.assertNotIn("secret-token", str(raised.exception.as_dict()))

    def test_incomplete_project_payload_is_rejected(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=[{"id": "ERP-1", "ProjectID": {"value": "P-1"}}],
            )

        source = AcumaticaProjectSource(
            AcumaticaProjectSourceSettings(
                base_url="https://erp.example.test",
                access_token="token",
                version="25.200.001",
            ),
            transport=httpx.MockTransport(handler),
        )
        with self.assertRaises(ApplicationOperationError) as raised:
            source.list_projects()
        self.assertEqual(raised.exception.code, "acumatica_project_payload_invalid")


if __name__ == "__main__":
    unittest.main()
