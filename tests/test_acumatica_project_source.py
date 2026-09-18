from __future__ import annotations

import unittest

import httpx

from app.application import ApplicationOperationError
from app.infrastructure.acumatica import AcumaticaProjectSource, AcumaticaProjectSourceSettings


LOGGER = "app.infrastructure.acumatica.project_source"


def _settings(**overrides) -> AcumaticaProjectSourceSettings:
    values = {
        "base_url": "https://erp.example.test/Instance",
        "bearer_token": "test-token",
        "endpoint": "Default",
        "version": "25.200.001",
        "entity": "Project",
        "page_size": 2,
        "timeout_seconds": 0.25,
    }
    values.update(overrides)
    return AcumaticaProjectSourceSettings(**values)


def _project(
    external_id: str,
    number: str,
    name: str,
    *,
    client: str | None = "Client",
    manager: str | None = "Gestionnaire",
    status: str | None = "Active",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": external_id,
        "ProjectID": {"value": number},
        "Description": {"value": name},
    }
    if client is not None:
        payload["Customer"] = {"value": client}
    if manager is not None:
        payload["ProjectManager"] = {"value": manager}
    if status is not None:
        payload["Status"] = {"value": status}
    return payload


class AcumaticaProjectSourceTests(unittest.TestCase):
    def test_reads_paginated_contract_rest_projects_and_never_exposes_token(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            self.assertEqual(request.headers.get("Authorization"), "Bearer test-token")
            skip = request.url.params.get("$skip")
            if skip == "0":
                payload = [
                    _project("ERP-1", "P-100", "Projet 100", client="Client A", manager="Alice"),
                    _project(
                        "ERP-2",
                        "P-200",
                        "Projet 200",
                        client="Client B",
                        manager="Bob",
                        status="Completed",
                    ),
                ]
            else:
                payload = [
                    _project(
                        "ERP-3",
                        "P-300",
                        "Projet 300",
                        client=None,
                        manager=None,
                        status="Inactive",
                    )
                ]
            return httpx.Response(200, json=payload)

        settings = _settings()
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
        self.assertEqual(requests[1].url.params.get("$skip"), "2")
        self.assertIn("ProjectID", requests[0].url.params.get("$select", ""))
        self.assertNotIn("test-token", repr(settings))
        self.assertNotIn("test-token", str(settings.safe_summary()))

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

        settings = _settings(
            base_url="https://erp.example.test",
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

    def test_optional_fields_may_be_absent_without_inventing_values(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=[_project("ERP-1", "P-1", "Projet minimal", client=None, manager=None, status=None)],
            )

        row = AcumaticaProjectSource(
            _settings(page_size=200),
            transport=httpx.MockTransport(handler),
        ).list_projects()[0]

        self.assertIsNone(row.client)
        self.assertIsNone(row.project_manager_name)
        self.assertEqual(row.status, "active")

    def test_http_failures_are_classified_without_leaking_body_or_token(self) -> None:
        cases = (
            (401, "authentication", False),
            (403, "authorization", False),
            (429, "throttled", True),
            (500, "upstream_5xx", True),
            (503, "upstream_5xx", True),
        )
        for status, failure_kind, retryable in cases:
            with self.subTest(status=status):
                def handler(_request: httpx.Request, status=status) -> httpx.Response:
                    return httpx.Response(status, text="sensitive-upstream-body")

                source = AcumaticaProjectSource(
                    _settings(bearer_token="secret-bearer-value"),
                    transport=httpx.MockTransport(handler),
                )
                with self.assertLogs(LOGGER, level="WARNING") as captured:
                    with self.assertRaises(ApplicationOperationError) as raised:
                        source.list_projects()

                self.assertEqual(raised.exception.code, "acumatica_project_read_failed")
                self.assertEqual(raised.exception.context["failure_kind"], failure_kind)
                self.assertEqual(raised.exception.context["http_status"], status)
                self.assertEqual(raised.exception.context["retryable"], retryable)
                diagnostic = str(raised.exception.as_dict()) + "\n" + "\n".join(captured.output)
                self.assertNotIn("sensitive-upstream-body", diagnostic)
                self.assertNotIn("secret-bearer-value", diagnostic)

    def test_timeout_and_network_errors_are_classified_and_safe(self) -> None:
        cases = (
            (
                "timeout",
                lambda request: httpx.ReadTimeout(
                    "sensitive-timeout-detail",
                    request=request,
                ),
            ),
            (
                "network",
                lambda request: httpx.ConnectError(
                    "sensitive-network-detail",
                    request=request,
                ),
            ),
        )
        for failure_kind, factory in cases:
            with self.subTest(failure_kind=failure_kind):
                def handler(request: httpx.Request, factory=factory):
                    raise factory(request)

                source = AcumaticaProjectSource(
                    _settings(bearer_token="secret-bearer-value"),
                    transport=httpx.MockTransport(handler),
                )
                with self.assertLogs(LOGGER, level="WARNING") as captured:
                    with self.assertRaises(ApplicationOperationError) as raised:
                        source.list_projects()

                self.assertEqual(raised.exception.code, "acumatica_project_read_failed")
                self.assertEqual(raised.exception.context["failure_kind"], failure_kind)
                self.assertTrue(raised.exception.context["retryable"])
                diagnostic = str(raised.exception.as_dict()) + "\n" + "\n".join(captured.output)
                self.assertNotIn("sensitive-timeout-detail", diagnostic)
                self.assertNotIn("sensitive-network-detail", diagnostic)
                self.assertNotIn("secret-bearer-value", diagnostic)

    def test_malformed_json_and_invalid_shapes_are_rejected(self) -> None:
        cases = (
            (
                httpx.Response(200, content=b"{not-json"),
                "invalid_json",
                "invalid_json",
            ),
            (
                httpx.Response(200, json={"items": []}),
                "invalid_payload",
                "not_a_list",
            ),
            (
                httpx.Response(200, json=[_project("ERP-1", "P-1", "Projet"), "bad-row"]),
                "invalid_payload",
                "non_object_row",
            ),
        )
        for response, failure_kind, reason in cases:
            with self.subTest(reason=reason):
                source = AcumaticaProjectSource(
                    _settings(page_size=200),
                    transport=httpx.MockTransport(lambda _request, response=response: response),
                )
                with self.assertRaises(ApplicationOperationError) as raised:
                    source.list_projects()

                self.assertEqual(raised.exception.code, "acumatica_project_response_invalid")
                self.assertEqual(raised.exception.context["failure_kind"], failure_kind)
                self.assertEqual(raised.exception.context["reason"], reason)

    def test_incomplete_required_project_payload_is_rejected_without_logging_payload(self) -> None:
        marker = "sensitive-project-name"

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=[{"id": "ERP-1", "ProjectID": {"value": "P-1"}, "Other": marker}],
            )

        source = AcumaticaProjectSource(
            _settings(page_size=200),
            transport=httpx.MockTransport(handler),
        )
        with self.assertLogs(LOGGER, level="WARNING") as captured:
            with self.assertRaises(ApplicationOperationError) as raised:
                source.list_projects()

        self.assertEqual(raised.exception.code, "acumatica_project_payload_invalid")
        self.assertNotIn(marker, "\n".join(captured.output))
        self.assertEqual(
            raised.exception.context,
            {"has_external_id": True, "has_number": True, "has_name": False},
        )

    def test_failure_on_later_page_never_returns_a_partial_snapshot(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if request.url.params.get("$skip") == "0":
                return httpx.Response(
                    200,
                    json=[
                        _project("ERP-1", "P-1", "Projet 1"),
                        _project("ERP-2", "P-2", "Projet 2"),
                    ],
                )
            return httpx.Response(503, text="page-two-sensitive-body")

        source = AcumaticaProjectSource(
            _settings(page_size=2),
            transport=httpx.MockTransport(handler),
        )

        with self.assertRaises(ApplicationOperationError) as raised:
            source.list_projects()

        self.assertEqual(calls, 2)
        self.assertEqual(raised.exception.context["failure_kind"], "upstream_5xx")
        self.assertEqual(raised.exception.context["http_status"], 503)


if __name__ == "__main__":
    unittest.main()
