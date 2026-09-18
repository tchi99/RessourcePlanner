from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReactCompetencyCatalogContractTests(unittest.TestCase):
    def test_api_contract_exposes_catalog_and_stable_ids(self) -> None:
        api = (ROOT / "frontend" / "src" / "api.ts").read_text(encoding="utf-8")

        self.assertIn("CompetencyReadModel", api)
        self.assertIn("competency_ids: string[]", api)
        self.assertIn("required_competency_ids: string[]", api)
        self.assertIn("required_competency_id: string | null", api)
        self.assertIn('"/api/v1/competencies"', api)
        self.assertIn("getCompetencies", api)
        self.assertIn("createCompetency", api)
        self.assertIn("updateCompetency", api)
        self.assertIn("deactivateCompetency", api)

    def test_searchable_selector_is_shared_by_resources_demands_and_segments(self) -> None:
        picker = (ROOT / "frontend" / "src" / "CompetencyPicker.tsx").read_text(
            encoding="utf-8"
        )
        resources = (ROOT / "frontend" / "src" / "ResourcesPage.tsx").read_text(
            encoding="utf-8"
        )
        demands = (ROOT / "frontend" / "src" / "DemandsPage.tsx").read_text(
            encoding="utf-8"
        )
        segments = (ROOT / "frontend" / "src" / "SegmentEditor.tsx").read_text(
            encoding="utf-8"
        )

        self.assertIn('type="search"', picker)
        self.assertIn("selectedIds", picker)
        self.assertIn("multiple={multiple}", picker)
        self.assertIn("<CompetencyPicker", resources)
        self.assertIn("<CompetencyPicker", demands)
        self.assertIn("<CompetencyPicker", segments)
        self.assertIn('multiple={false}', segments)
        self.assertNotIn("capacity_hours", picker)
        self.assertNotIn("eligible", picker)

    def test_resource_page_hosts_catalog_administration(self) -> None:
        resources = (ROOT / "frontend" / "src" / "ResourcesPage.tsx").read_text(
            encoding="utf-8"
        )
        panel = (ROOT / "frontend" / "src" / "CompetencyCatalogPanel.tsx").read_text(
            encoding="utf-8"
        )

        self.assertIn("<CompetencyCatalogPanel", resources)
        self.assertIn("Catalogue de compétences", panel)
        self.assertIn("await createCompetency", panel)
        self.assertIn("await updateCompetency", panel)
        self.assertIn("await deactivateCompetency", panel)
        self.assertIn("Les IDs restent stables", panel)


if __name__ == "__main__":
    unittest.main()
