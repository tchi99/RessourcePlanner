from __future__ import annotations

from pathlib import Path
import unittest

import httpx

from app.application import ApplicationOperationError
from app.infrastructure.acumatica import (
    ODataEmployeeSource,
    ODataEmployeeSourceSettings,
    parse_rp_employees_feed,
)


FIXTURE = Path("tests/fixtures/acumatica/rp_employees_atom.xml")


def _entry(employee_id: str, *, status: str = "Actif") -> str:
    return f"""
  <entry>
    <category term="PX.Data.RP_Employees" />
    <content type="application/xml"><m:properties>
      <d:EmployeID xml:space="preserve"> {employee_id} </d:EmployeID>
      <d:DisplayName>Employé {employee_id}</d:DisplayName>
      <d:Email>{employee_id.lower()}@example.invalid</d:Email>
      <d:Status>{status}</d:Status>
      <d:DepartmentCodeDescription>Automatisation</d:DepartmentCodeDescription>
      <d:DepartementCode>AUTO</d:DepartementCode>
      <d:EmployeeClass>GENERAL</d:EmployeeClass>
      <d:SupervisordID m:null="true" />
      <d:Telephone m:null="true" />
      <d:BranchCode xml:space="preserve"> 210 </d:BranchCode>
      <d:ContactID m:type="Edm.Int32">42</d:ContactID>
    </m:properties></content>
  </entry>"""


def _feed(*employee_ids: str) -> bytes:
    entries = "".join(_entry(employee_id) for employee_id in employee_ids)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices"
      xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">
{entries}
</feed>""".encode("utf-8")


class ODataEmployeeSourceTests(unittest.TestCase):
    def test_contract_fixture_parses_stable_identity_and_erp_attributes(self) -> None:
        rows = parse_rp_employees_feed(FIXTURE.read_bytes())

        alice = next(row for row in rows if row.employee_id == "EXEMALIC")
        self.assertEqual(alice.display_name, "1001 - ALICE EXEMPLE")
        self.assertEqual(alice.department_code, "TECHAUTO")
        self.assertEqual(alice.branch_code, "210")
        self.assertEqual(alice.supervisor_id, "DEMOALEX")
        self.assertEqual(alice.contact_id, 900001)
        self.assertEqual(alice.status, "Actif")

        inactive = next(row for row in rows if row.employee_id == "FICTDANI")
        self.assertEqual(inactive.status, "Inactif")
        self.assertIsNone(inactive.supervisor_id)

        no_phone = next(row for row in rows if row.employee_id == "UTILFRED")
        self.assertIsNone(no_phone.telephone)

    def test_source_maps_erp_status_without_granting_local_activation_semantics(self) -> None:
        source = ODataEmployeeSource(
            ODataEmployeeSourceSettings(
                base_url="https://erp.example.test/Instance",
                page_size=100,
            ),
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, content=FIXTURE.read_bytes())
            ),
        )

        rows = source.list_employees()
        active = next(row for row in rows if row.external_id == "EXEMALIC")
        inactive = next(row for row in rows if row.external_id == "FICTDANI")
        self.assertTrue(active.erp_active)
        self.assertFalse(inactive.erp_active)
        self.assertEqual(active.branch_code, "210")
        self.assertEqual(active.erp_status, "Actif")

    def test_source_reuses_observed_top_skip_pagination(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            skip = request.url.params.get("$skip")
            if skip == "0":
                return httpx.Response(200, content=_feed("EMP-A", "EMP-B"))
            if skip == "2":
                return httpx.Response(200, content=_feed("EMP-C"))
            self.fail(f"unexpected skip: {skip}")

        source = ODataEmployeeSource(
            ODataEmployeeSourceSettings(
                base_url="https://erp.example.test/Instance",
                username="odata-user",
                credential="dummy-passphrase",
                page_size=2,
            ),
            transport=httpx.MockTransport(handler),
        )

        rows = source.list_employees()

        self.assertEqual([row.external_id for row in rows], ["EMP-A", "EMP-B", "EMP-C"])
        self.assertEqual(len(requests), 2)
        for request, expected_skip in zip(requests, ("0", "2"), strict=True):
            self.assertEqual(request.url.params.get("$orderby"), "EmployeID asc")
            self.assertEqual(request.url.params.get("$top"), "2")
            self.assertEqual(request.url.params.get("$skip"), expected_skip)
            self.assertTrue(request.headers.get("Authorization", "").startswith("Basic "))
        self.assertNotIn("odata-user", repr(source._settings))
        self.assertNotIn("dummy-passphrase", repr(source._settings))

    def test_duplicate_employee_across_pages_fails_closed(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.params.get("$skip") == "0":
                return httpx.Response(200, content=_feed("EMP-A"))
            return httpx.Response(200, content=_feed("EMP-A"))

        source = ODataEmployeeSource(
            ODataEmployeeSourceSettings(
                base_url="https://erp.example.test/Instance",
                page_size=1,
            ),
            transport=httpx.MockTransport(handler),
        )

        with self.assertRaises(ApplicationOperationError) as raised:
            source.list_employees()

        self.assertEqual(raised.exception.code, "acumatica_employee_response_invalid")
        self.assertEqual(
            raised.exception.context["reason"],
            "pagination_duplicate_employee",
        )

    def test_invalid_late_entry_rejects_complete_page_before_sync(self) -> None:
        invalid = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices"
      xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">
  <entry><content type="application/xml"><m:properties>
    <d:EmployeID>EMP-A</d:EmployeID><d:DisplayName>A</d:DisplayName><d:Status>Actif</d:Status>
  </m:properties></content></entry>
  <entry><content type="application/xml"><m:properties>
    <d:EmployeID>EMP-B</d:EmployeID><d:Status>Actif</d:Status>
  </m:properties></content></entry>
</feed>"""
        source = ODataEmployeeSource(
            ODataEmployeeSourceSettings(base_url="https://erp.example.test/Instance"),
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, content=invalid)
            ),
        )

        with self.assertRaises(ApplicationOperationError) as raised:
            source.list_employees()

        self.assertEqual(raised.exception.context["reason"], "required_field_missing")
        self.assertEqual(raised.exception.context["field"], "DisplayName")
        self.assertEqual(raised.exception.context["entry_index"], 1)


if __name__ == "__main__":
    unittest.main()
