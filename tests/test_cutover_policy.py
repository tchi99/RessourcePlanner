from __future__ import annotations

import unittest

from app.domain.cutover_policy import (
    GUARDED_PURE_MODE,
    LEGACY_MODE,
    PURE_MODE,
    evaluate_cutover_gate,
    normalize_planning_engine_mode,
)


class CutoverPolicyTests(unittest.TestCase):
    def test_default_mode_is_pure(self) -> None:
        self.assertEqual(normalize_planning_engine_mode(None), PURE_MODE)
        self.assertEqual(normalize_planning_engine_mode(""), PURE_MODE)

    def test_pure_mode_is_accepted_case_insensitively(self) -> None:
        self.assertEqual(normalize_planning_engine_mode("PURE"), PURE_MODE)

    def test_guarded_mode_is_accepted_case_insensitively(self) -> None:
        self.assertEqual(normalize_planning_engine_mode("GUARDED_PURE"), GUARDED_PURE_MODE)

    def test_unknown_explicit_mode_falls_back_to_legacy(self) -> None:
        self.assertEqual(normalize_planning_engine_mode("typo"), LEGACY_MODE)

    def test_exact_shadow_match_allows_pure_engine(self) -> None:
        decision = evaluate_cutover_gate(shadow_matches=True, unsupported_segment_count=0)
        self.assertTrue(decision.use_pure_engine)
        self.assertEqual(decision.reason, "shadow_match")

    def test_shadow_mismatch_keeps_legacy(self) -> None:
        decision = evaluate_cutover_gate(shadow_matches=False, unsupported_segment_count=0)
        self.assertFalse(decision.use_pure_engine)
        self.assertEqual(decision.reason, "shadow_mismatch")

    def test_unsupported_segments_keep_legacy_even_when_comparable_part_matches(self) -> None:
        decision = evaluate_cutover_gate(shadow_matches=True, unsupported_segment_count=1)
        self.assertFalse(decision.use_pure_engine)
        self.assertEqual(decision.reason, "unsupported_segments")


if __name__ == "__main__":
    unittest.main()
