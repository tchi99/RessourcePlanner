from __future__ import annotations

from pathlib import Path
import unittest

from app.infrastructure.acumatica.odata_atom import (
    ATOM_NAMESPACE,
    DATA_NAMESPACE,
    METADATA_NAMESPACE,
    ODataAtomFeedError,
    parse_atom_feed,
)


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "acumatica" / "rp_projects_atom.xml"


class ODataAtomPrimitiveTests(unittest.TestCase):
    def test_project_fixture_exposes_common_structure_types_and_nullability(self) -> None:
        feed = parse_atom_feed(FIXTURE.read_bytes())

        self.assertEqual(feed.title, "RP_Projects")
        self.assertEqual(len(feed.entries), 5)
        self.assertIn(("", ATOM_NAMESPACE), feed.namespaces)
        self.assertIn(("d", DATA_NAMESPACE), feed.namespaces)
        self.assertIn(("m", METADATA_NAMESPACE), feed.namespaces)

        first = {prop.name: prop for prop in feed.entries[0].properties}
        self.assertEqual(first["ProjectId"].edm_type, "Edm.Int32")
        self.assertEqual(first["ProjectId"].value, "101")
        self.assertEqual(first["ProjectCode"].value, "P-0100")
        self.assertTrue(first["ProjectCode"].preserves_space)
        self.assertEqual(first["EndDate"].edm_type, "Edm.DateTime")
        self.assertTrue(first["EndDate"].is_null)
        self.assertIsNone(first["EndDate"].value)

    def test_prefixes_are_irrelevant_and_entity_self_link_metadata_is_observed(self) -> None:
        payload = """<?xml version="1.0" encoding="utf-8"?>
<a:feed xmlns:a="http://www.w3.org/2005/Atom"
        xmlns:data="http://schemas.microsoft.com/ado/2007/08/dataservices"
        xmlns:meta="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">
  <a:title>SyntheticFeed</a:title>
  <a:entry>
    <a:category term="PX.Data.SyntheticContract" />
    <a:link rel="self" href="synthetic" />
    <a:content type="application/xml">
      <meta:properties>
        <data:StableId meta:type="Edm.Int32">42</data:StableId>
        <data:OptionalText meta:null="true" />
      </meta:properties>
    </a:content>
  </a:entry>
</a:feed>"""

        feed = parse_atom_feed(payload)

        self.assertEqual(feed.title, "SyntheticFeed")
        self.assertEqual(feed.entity_types, ("PX.Data.SyntheticContract",))
        self.assertTrue(feed.has_self_links)
        values = feed.entries[0].values()
        self.assertEqual(values["StableId"], "42")
        self.assertIsNone(values["OptionalText"])

    def test_invalid_xml_and_non_atom_roots_fail_without_payload_values(self) -> None:
        marker = "confidential-business-value"
        cases = (
            (f"<feed>{marker}", "invalid_xml"),
            (f"<html><body>{marker}</body></html>", "invalid_feed_root"),
        )
        for payload, reason in cases:
            with self.subTest(reason=reason):
                with self.assertRaises(ODataAtomFeedError) as raised:
                    parse_atom_feed(payload)
                self.assertEqual(raised.exception.reason, reason)
                self.assertNotIn(marker, str(raised.exception))

    def test_entry_without_properties_is_rejected_with_entry_index(self) -> None:
        payload = """<feed xmlns="http://www.w3.org/2005/Atom"><entry /></feed>"""

        with self.assertRaises(ODataAtomFeedError) as raised:
            parse_atom_feed(payload)

        self.assertEqual(raised.exception.reason, "properties_missing")
        self.assertEqual(raised.exception.entry_index, 0)


if __name__ == "__main__":
    unittest.main()
