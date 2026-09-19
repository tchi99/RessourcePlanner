from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReactMediumTermUnlinkedSegmentsContractTests(unittest.TestCase):
    def test_medium_term_loads_unlinked_projection(self) -> None:
        page = (ROOT / "frontend" / "src" / "MediumTermPage.tsx").read_text(encoding="utf-8")
        api = (ROOT / "frontend" / "src" / "api.ts").read_text(encoding="utf-8")

        self.assertIn("getMediumTermUnlinkedSegments", page)
        self.assertIn("<MediumTermUnlinkedSegmentsPanel", page)
        self.assertIn("MediumTermUnlinkedSegmentReadModel", api)
        self.assertIn("/api/v1/medium-term/unlinked-segments", api)

    def test_panel_distinguishes_anomalies_from_legitimate_ad_hoc(self) -> None:
        panel = (
            ROOT / "frontend" / "src" / "MediumTermUnlinkedSegmentsPanel.tsx"
        ).read_text(encoding="utf-8")

        self.assertIn("Demande sans WorkPackage", panel)
        self.assertIn("Ad hoc légitime", panel)
        self.assertIn("Référence WorkPackage invalide", panel)
        self.assertIn("Anomalies", panel)
        self.assertIn("Ad hoc légitimes", panel)

    def test_panel_uses_canonical_mutations_for_explicit_linking(self) -> None:
        panel = (
            ROOT / "frontend" / "src" / "MediumTermUnlinkedSegmentsPanel.tsx"
        ).read_text(encoding="utf-8")

        self.assertIn("linkDemandToWorkPackage", panel)
        self.assertIn("updateSegment", panel)
        self.assertIn("reapproval_on_link", panel)
        self.assertIn("Ouvrir le segment", panel)
        self.assertIn("Voir la demande", panel)


if __name__ == "__main__":
    unittest.main()
