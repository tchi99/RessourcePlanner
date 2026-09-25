from __future__ import annotations

from datetime import timezone
from pathlib import Path
import unittest

import httpx

from app.application import ApplicationOperationError
from app.infrastructure.acumatica import (
    ODataProjectFeedError,
    ODataProjectSource,
    ODataProjectSourceSettings,
    parse_rp_projects_feed,
)


LOGGER = "app.infrastructure.acumatica.odata_project_source"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "acumatica" / "rp_projects_atom.xml"


def _settings(**overrides) -> ODataProjectSourceSettings:
    values = {
        "base_url": "https://erp.example.test/Instance",
        "timeout_seconds": 0.25,
    }
    values.update(overrides)
    return ODataProjectSourceSettings(**values)


def _feed(properties: str = "", *, entry: bool = True) -> bytes:
    body = (
        f"<entry><content type=\"application/xml\"><m:properties>{properties}"
        "</m:properties></content></entry>"
        if entry
        else ""
    )
    return (
        "<?xml version=\"1.0\" encoding=\"utf-8\"?>"
        "<feed xmlns=\"http://www.w3.org/2005/Atom\" "
        "xmlns:d=\"http://schemas.microsoft.com/ado/2007/08/dataservices\" "
        "xmlns:m=\"http://schemas.microsoft.com/ado/2007/08/dataservices/metadata\">"
        f"{body}</feed>"
    ).encode("utf-8")


def _feed_entries(*properties_blocks: str) -> bytes:
    body = "".join(
        "<entry><content type=\"application/xml\"><m:properties>"
        + properties
        + "</m:properties></content></entry>"
        for properties in properties_blocks
    )
    return (
        "<?xml version=\"1.0\" encoding=\"utf-8\"?>"
        "<feed xmlns=\"http://www.w3.org/2005/Atom\" "
        "xmlns:d=\"http://schemas.microsoft.com/ado/2007/08/dataservices\" "
        "xmlns:m=\"http://schemas.microsoft.com/ado/2007/08/dataservices/metadata\">"
        f"{body}</feed>"
    ).encode("utf-8")


def _minimal_properties(
    *,
    project_id: str = "101",
    project_code: str = " P-0100 ",
    project_name: str = "Projet Énergie",
) -> str:
    return (
        f"<d:ProjectId m:type=\"Edm.Int32\">{project_id}</d:ProjectId>"
        f"<d:ProjectCode xml:space=\"preserve\">{project_code}</d:ProjectCode>"
        f"<d:ProjectName>{project_name}</d:ProjectName>"
    )


class ODataProjectContractTests(unittest.TestCase):
    def test_anonymized_fixture_covers_rp_projects_contract(self) -> None:
        rows = parse_rp_projects_feed(FIXTURE.read_bytes())

        self.assertEqual(len(rows), 5)
        first = rows[0]
        self.assertEqual(first.project_id, 101)
        self.assertEqual(first.project_code, "P-0100")
        self.assertEqual(first.project_name, "Projet Électrique – Montréal")
        self.assertEqual(first.customer_id, "C-001")
        self.assertEqual(first.customer_name, "Client Énergie")
        self.assertEqual(first.project_manager_id, "PM-01")
        self.assertEqual(first.project_manager_name, "Élodie Tremblay")
        self.assertEqual(first.status, "Actif")
        self.assertEqual(first.start_date.isoformat(), "2026-01-15T00:00:00")
        self.assertIsNone(first.end_date)
        self.assertEqual(first.default_branch_code, "110")
        self.assertEqual(first.default_branch_description, "Électrique")
        self.assertEqual(first.last_modified_at.isoformat(), "2026-09-24T12:30:45.123000")
        self.assertEqual(first.base_type, "P")

        self.assertEqual(rows[1].base_type, "R")
        self.assertIsNone(rows[1].customer_id)
        self.assertIsNone(rows[1].project_manager_id)
        self.assertIsNone(rows[1].project_manager_name)
        self.assertEqual(rows[1].end_date.isoformat(), "2026-12-31T17:00:00")
        self.assertEqual(
            [row.status for row in rows],
            ["Actif", "En planification", "Complété", "Suspendu", "Annulé"],
        )
        self.assertEqual(
            [row.default_branch_code for row in rows],
            ["110", "210", "310", "510", "910"],
        )

    def test_namespace_prefixes_and_property_order_are_not_significant(self) -> None:
        payload = StringPayload.ALTERNATE_PREFIXES.encode("utf-8")

        row = parse_rp_projects_feed(payload)[0]

        self.assertEqual(row.project_id, 214)
        self.assertEqual(row.project_code, "P-0214")
        self.assertEqual(row.project_name, "Projet Québec")
        self.assertEqual(row.customer_name, "Client Côte-Nord")
        self.assertEqual(row.default_branch_code, "210")
        self.assertEqual(row.base_type, "R")
        self.assertEqual(row.last_modified_at.tzinfo, timezone.utc)

    def test_valid_feed_without_entries_returns_empty_snapshot(self) -> None:
        self.assertEqual(parse_rp_projects_feed(_feed(entry=False)), ())

    def test_invalid_xml_is_rejected_without_payload_details(self) -> None:
        with self.assertRaises(ODataProjectFeedError) as raised:
            parse_rp_projects_feed(b"<feed>sensitive-project-payload")

        self.assertEqual(raised.exception.reason, "invalid_xml")
        self.assertNotIn("sensitive-project-payload", str(raised.exception))

    def test_well_formed_non_atom_xml_is_not_treated_as_empty_snapshot(self) -> None:
        with self.assertRaises(ODataProjectFeedError) as raised:
            parse_rp_projects_feed(b"<html><body>login page</body></html>")

        self.assertEqual(raised.exception.reason, "invalid_feed_root")

    def test_required_fields_are_rejected_explicitly(self) -> None:
        cases = {
            "ProjectId": (
                "<d:ProjectCode>P-1</d:ProjectCode><d:ProjectName>Projet</d:ProjectName>"
            ),
            "ProjectCode": (
                "<d:ProjectId m:type=\"Edm.Int32\">1</d:ProjectId>"
                "<d:ProjectName>Projet</d:ProjectName>"
            ),
            "ProjectName": (
                "<d:ProjectId m:type=\"Edm.Int32\">1</d:ProjectId>"
                "<d:ProjectCode>P-1</d:ProjectCode>"
            ),
        }
        for field, properties in cases.items():
            with self.subTest(field=field):
                with self.assertRaises(ODataProjectFeedError) as raised:
                    parse_rp_projects_feed(_feed(properties))
                self.assertEqual(raised.exception.reason, "required_field_missing")
                self.assertEqual(raised.exception.field, field)
                self.assertEqual(raised.exception.entry_index, 0)

    def test_invalid_int32_and_datetime_values_are_rejected(self) -> None:
        cases = (
            (
                _minimal_properties(project_id="not-an-int"),
                "invalid_int32",
                "ProjectId",
            ),
            (
                _minimal_properties(project_id=str(2**31)),
                "invalid_int32",
                "ProjectId",
            ),
            (
                _minimal_properties() + "<d:StartDate m:type=\"Edm.DateTime\">not-a-date</d:StartDate>",
                "invalid_datetime",
                "StartDate",
            ),
            (
                _minimal_properties()
                + "<d:LastModifiedDateTime m:type=\"Edm.DateTime\">2026-99-99T00:00:00</d:LastModifiedDateTime>",
                "invalid_datetime",
                "LastModifiedDateTime",
            ),
        )
        for properties, reason, field in cases:
            with self.subTest(reason=reason, field=field):
                with self.assertRaises(ODataProjectFeedError) as raised:
                    parse_rp_projects_feed(_feed(properties))
                self.assertEqual(raised.exception.reason, reason)
                self.assertEqual(raised.exception.field, field)

    def test_source_maps_project_id_to_stable_external_identity_without_fixed_auth(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            self.assertEqual(request.headers.get("X-Test-Credential"), "opaque-test-value")
            return httpx.Response(200, content=FIXTURE.read_bytes())

        source = ODataProjectSource(
            _settings(),
            transport=httpx.MockTransport(handler),
            request_headers={"X-Test-Credential": "opaque-test-value"},
        )

        rows = source.list_projects()

        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0].external_id, "101")
        self.assertEqual(rows[0].number, "P-0100")
        self.assertEqual(rows[0].name, "Projet Électrique – Montréal")
        self.assertEqual(rows[0].client, "Client Énergie")
        self.assertEqual(rows[0].project_manager_external_id, "PM-01")
        self.assertEqual(rows[0].project_manager_name, "Élodie Tremblay")
        self.assertEqual(rows[0].status, "Actif")
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].url.path, "/Instance/oDATA/RP_Projects")
        self.assertIn("application/atom+xml", requests[0].headers["Accept"])
        self.assertEqual(
            source._settings.safe_summary(),
            {
                "protocol": "odata",
                "feed_path": "/oDATA/RP_Projects",
                "authentication": "none",
                "pagination": {
                    "mode": "top_skip",
                    "orderby": "ProjectId asc",
                    "page_size": 100,
                },
            },
        )
        self.assertNotIn("opaque-test-value", repr(source._settings))

    def test_source_uses_basic_auth_and_observed_top_skip_pagination(self) -> None:
        requests: list[httpx.Request] = []
        first_page = _feed_entries(
            _minimal_properties(project_id="101", project_code="P-0101", project_name="Projet 101"),
            _minimal_properties(project_id="102", project_code="P-0102", project_name="Projet 102"),
        )
        second_page = _feed_entries(
            _minimal_properties(project_id="103", project_code="P-0103", project_name="Projet 103"),
        )

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            self.assertTrue(request.headers.get("Authorization", "").startswith("Basic "))
            skip = request.url.params.get("$skip")
            if skip == "0":
                return httpx.Response(200, content=first_page)
            if skip == "2":
                return httpx.Response(200, content=second_page)
            self.fail(f"unexpected pagination offset: {skip}")

        settings = _settings(
            username="odata-user",
            credential="dummy-passphrase",
            page_size=2,
        )
        source = ODataProjectSource(
            settings,
            transport=httpx.MockTransport(handler),
        )

        rows = source.list_projects()

        self.assertEqual([row.external_id for row in rows], ["101", "102", "103"])
        self.assertEqual(len(requests), 2)
        for request, expected_skip in zip(requests, ("0", "2"), strict=True):
            self.assertEqual(request.url.params.get("$orderby"), "ProjectId asc")
            self.assertEqual(request.url.params.get("$top"), "2")
            self.assertEqual(request.url.params.get("$skip"), expected_skip)
        self.assertEqual(
            settings.safe_summary(),
            {
                "protocol": "odata",
                "feed_path": "/oDATA/RP_Projects",
                "authentication": "basic",
                "pagination": {
                    "mode": "top_skip",
                    "orderby": "ProjectId asc",
                    "page_size": 2,
                },
            },
        )
        diagnostic = repr(settings) + str(settings.safe_summary())
        self.assertNotIn("odata-user", diagnostic)
        self.assertNotIn("dummy-passphrase", diagnostic)

    def test_duplicate_project_across_pages_fails_closed(self) -> None:
        page = _feed_entries(
            _minimal_properties(project_id="101", project_code="P-0101", project_name="Projet 101"),
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=page)

        source = ODataProjectSource(
            _settings(page_size=1),
            transport=httpx.MockTransport(handler),
        )
        with self.assertLogs(LOGGER, level="WARNING") as captured:
            with self.assertRaises(ApplicationOperationError) as raised:
                source.list_projects()

        self.assertEqual(raised.exception.code, "acumatica_project_response_invalid")
        self.assertEqual(
            raised.exception.context["reason"],
            "pagination_duplicate_project",
        )
        self.assertNotIn("P-0101", str(raised.exception.as_dict()))
        self.assertNotIn("Projet 101", "\n".join(captured.output))

    def test_http_failures_are_classified_without_leaking_body_or_headers(self) -> None:
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

                source = ODataProjectSource(
                    _settings(),
                    transport=httpx.MockTransport(handler),
                    request_headers={"Cookie": "session=secret-cookie-value"},
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
                self.assertNotIn("secret-cookie-value", diagnostic)

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

                source = ODataProjectSource(
                    _settings(),
                    transport=httpx.MockTransport(handler),
                    request_headers={"Authorization": "opaque secret-header-value"},
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
                self.assertNotIn("secret-header-value", diagnostic)

    def test_invalid_feed_diagnostics_never_include_project_payload_or_secret(self) -> None:
        marker = "sensitive-project-payload"
        sensitive_value = "secret-cookie-value"

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=f"<feed>{marker}".encode("utf-8"))

        source = ODataProjectSource(
            _settings(),
            transport=httpx.MockTransport(handler),
            request_headers={"Cookie": f"session={sensitive_value}"},
        )
        with self.assertLogs(LOGGER, level="WARNING") as captured:
            with self.assertRaises(ApplicationOperationError) as raised:
                source.list_projects()

        self.assertEqual(raised.exception.code, "acumatica_project_response_invalid")
        self.assertEqual(raised.exception.context["failure_kind"], "invalid_payload")
        self.assertEqual(raised.exception.context["reason"], "invalid_xml")
        diagnostic = str(raised.exception.as_dict()) + "\n" + "\n".join(captured.output)
        self.assertNotIn(marker, diagnostic)
        self.assertNotIn(sensitive_value, diagnostic)


class StringPayload:
    ALTERNATE_PREFIXES = """<?xml version="1.0" encoding="utf-8"?>
<a:feed xmlns:a="http://www.w3.org/2005/Atom"
        xmlns:data="http://schemas.microsoft.com/ado/2007/08/dataservices"
        xmlns:meta="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">
  <a:entry>
    <a:content type="application/xml">
      <meta:properties>
        <data:BaseType>R</data:BaseType>
        <data:LastModifiedDateTime meta:type="Edm.DateTime">2026-09-24T18:00:00Z</data:LastModifiedDateTime>
        <data:CustomerName>Client Côte-Nord</data:CustomerName>
        <data:ProjectName>Projet Québec</data:ProjectName>
        <data:DefaultBranchCode>210</data:DefaultBranchCode>
        <data:ProjectCode xml:space="preserve"> P-0214 </data:ProjectCode>
        <data:ProjectId meta:type="Edm.Int32">214</data:ProjectId>
      </meta:properties>
    </a:content>
  </a:entry>
</a:feed>"""


if __name__ == "__main__":
    unittest.main()
