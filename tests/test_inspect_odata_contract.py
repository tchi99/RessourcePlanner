from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.inspect_odata_contract import inspect_odata_contract, inspect_odata_file, main


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "acumatica" / "rp_projects_atom.xml"


class ODataContractInspectorTests(unittest.TestCase):
    def test_project_fixture_report_contains_structure_but_no_business_values(self) -> None:
        report = inspect_odata_file(FIXTURE)

        self.assertIn("Feed format: Atom/XML", report)
        self.assertIn("Entries: 5", report)
        self.assertIn("Title: RP_Projects", report)
        self.assertIn("ProjectId: Edm.Int32", report)
        self.assertIn("EndDate: Edm.DateTime", report)
        self.assertIn("m:null: yes", report)
        self.assertIn("xml:space=preserve: yes", report)

        for value in (
            "P-0100",
            "Client Énergie",
            "Élodie Tremblay",
            "Projet Électrique",
        ):
            self.assertNotIn(value, report)

    def test_sensitive_property_values_never_appear_in_report(self) -> None:
        markers = (
            "Highly Sensitive Person Name",
            "private-person@example.invalid",
            "CONFIDENTIAL-EMPLOYEE-0007",
        )
        payload = f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices"
      xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">
  <entry>
    <category term="PX.Data.SyntheticContract" />
    <link rel="self" href="synthetic" />
    <content type="application/xml">
      <m:properties>
        <d:DisplayName>{markers[0]}</d:DisplayName>
        <d:Contact>{markers[1]}</d:Contact>
        <d:StableKey xml:space="preserve">{markers[2]}</d:StableKey>
        <d:Optional m:null="true" />
      </m:properties>
    </content>
  </entry>
</feed>"""

        report = inspect_odata_contract(payload)

        self.assertIn("Entity: PX.Data.SyntheticContract", report)
        self.assertIn("DisplayName: string (implicit)", report)
        self.assertIn("Atom self links: yes", report)
        for marker in markers:
            self.assertNotIn(marker, report)

    def test_cli_invalid_xml_reports_only_structural_error(self) -> None:
        marker = "secret-payload-value"
        with TemporaryDirectory() as directory:
            path = Path(directory) / "sample.xml"
            path.write_text(f"<feed>{marker}", encoding="utf-8")
            stdout = StringIO()
            stderr = StringIO()

            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = main([str(path)])

        self.assertEqual(code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("invalid_xml", stderr.getvalue())
        self.assertNotIn(marker, stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
