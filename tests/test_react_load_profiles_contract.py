from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"


class ReactLoadProfilesContractTests(unittest.TestCase):
    def test_segment_api_exposes_closed_load_profile_contract(self) -> None:
        source = (FRONTEND / "segments-api.ts").read_text(encoding="utf-8")
        self.assertIn('"UNIFORM" | "FRONT_LOADED" | "BACK_LOADED" | "BELL"', source)
        self.assertIn("load_profile?: LoadProfile", source)

    def test_segment_editor_defaults_to_uniform_and_exposes_all_profiles(self) -> None:
        source = (FRONTEND / "SegmentEditor.tsx").read_text(encoding="utf-8")
        self.assertIn('load_profile: "UNIFORM"', source)
        self.assertIn('value="UNIFORM"', source)
        self.assertIn('value="FRONT_LOADED"', source)
        self.assertIn('value="BACK_LOADED"', source)
        self.assertIn('value="BELL"', source)
        self.assertIn("load_profile: form.load_profile", source)
        self.assertIn("quarts manuels/verrouillés restent prioritaires", source)
        self.assertIn("capacité/disponibilité demeure autoritaire", source)

    def test_segment_cards_make_profile_visible_without_recalculating_it(self) -> None:
        source = (FRONTEND / "DemandSegmentsPage.tsx").read_text(encoding="utf-8")
        self.assertIn("loadProfileLabel", source)
        self.assertIn('case "FRONT_LOADED"', source)
        self.assertIn('case "BACK_LOADED"', source)
        self.assertIn('case "BELL"', source)
        self.assertNotIn("spread_profile_hours", source)
        self.assertNotIn("load_profile_weights", source)


if __name__ == "__main__":
    unittest.main()
