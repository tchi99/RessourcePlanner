from __future__ import annotations

import unittest

import httpx

from app.infrastructure.acumatica.odata_atom import ODataAtomFeedError, parse_atom_feed
from tests.acumatica_odata_test_support import ODataMockRoute, ODataMockTransport


ATOM_EMPTY = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices"
      xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata" />"""


class ODataMockTransportTests(unittest.TestCase):
    def test_routes_can_match_filter_orderby_top_skip_and_multiple_pages(self) -> None:
        expected_filter = "Status eq 'Active'"
        fake = ODataMockTransport(
            ODataMockRoute(
                path="/oDATA/Synthetic",
                query={
                    "$filter": expected_filter,
                    "$orderby": "StableId asc",
                    "$top": "2",
                    "$skip": "0",
                },
                content=b"page-zero",
            ),
            ODataMockRoute(
                path="/oDATA/Synthetic",
                query={
                    "$filter": expected_filter,
                    "$orderby": "StableId asc",
                    "$top": "2",
                    "$skip": "2",
                },
                content=b"page-two",
            ),
        )

        with httpx.Client(transport=fake.transport, base_url="https://example.test") as client:
            first = client.get(
                "/oDATA/Synthetic",
                params={
                    "$filter": expected_filter,
                    "$orderby": "StableId asc",
                    "$top": "2",
                    "$skip": "0",
                },
            )
            second = client.get(
                "/oDATA/Synthetic",
                params={
                    "$filter": expected_filter,
                    "$orderby": "StableId asc",
                    "$top": "2",
                    "$skip": "2",
                },
            )

        self.assertEqual(first.content, b"page-zero")
        self.assertEqual(second.content, b"page-two")
        self.assertEqual(len(fake.requests), 2)

    def test_http_statuses_are_returned_without_an_erp_server(self) -> None:
        for status in (401, 403, 429, 500, 503):
            with self.subTest(status=status):
                fake = ODataMockTransport(
                    ODataMockRoute(status_code=status, content=b"synthetic")
                )
                with httpx.Client(
                    transport=fake.transport,
                    base_url="https://example.test",
                ) as client:
                    response = client.get("/oDATA/Synthetic")
                self.assertEqual(response.status_code, status)

    def test_timeout_and_network_failures_are_synthetic(self) -> None:
        cases = (
            ("timeout", httpx.ReadTimeout),
            ("network", httpx.ConnectError),
        )
        for failure, error_type in cases:
            with self.subTest(failure=failure):
                fake = ODataMockTransport(ODataMockRoute(failure=failure))
                with httpx.Client(
                    transport=fake.transport,
                    base_url="https://example.test",
                ) as client:
                    with self.assertRaises(error_type):
                        client.get("/oDATA/Synthetic")

    def test_invalid_xml_can_be_injected_into_the_real_parser(self) -> None:
        fake = ODataMockTransport(
            ODataMockRoute(content=b"<feed>not-valid")
        )
        with httpx.Client(
            transport=fake.transport,
            base_url="https://example.test",
        ) as client:
            payload = client.get("/oDATA/Synthetic").content

        with self.assertRaises(ODataAtomFeedError) as raised:
            parse_atom_feed(payload)

        self.assertEqual(raised.exception.reason, "invalid_xml")

    def test_valid_atom_xml_can_be_injected_into_the_real_parser(self) -> None:
        fake = ODataMockTransport(ODataMockRoute(content=ATOM_EMPTY))
        with httpx.Client(
            transport=fake.transport,
            base_url="https://example.test",
        ) as client:
            payload = client.get("/oDATA/Synthetic").content

        self.assertEqual(parse_atom_feed(payload).entries, ())


if __name__ == "__main__":
    unittest.main()
