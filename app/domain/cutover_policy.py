from __future__ import annotations

from dataclasses import dataclass


LEGACY_MODE = "legacy"
GUARDED_PURE_MODE = "guarded_pure"
SUPPORTED_MODES = {LEGACY_MODE, GUARDED_PURE_MODE}


@dataclass(frozen=True)
class CutoverGateDecision:
    use_pure_engine: bool
    reason: str


def normalize_planning_engine_mode(value: object) -> str:
    mode = str(value or LEGACY_MODE).strip().lower()
    return mode if mode in SUPPORTED_MODES else LEGACY_MODE


def evaluate_cutover_gate(*, shadow_matches: bool, unsupported_segment_count: int) -> CutoverGateDecision:
    """Decide whether the guarded cutover may persist the pure-engine plan.

    The legacy rebuild remains authoritative whenever the pure-engine comparison is
    incomplete or differs. This function is deliberately free of Excel/UI concerns so
    the safety policy can be covered by deterministic tests.
    """
    if int(unsupported_segment_count) > 0:
        return CutoverGateDecision(False, "unsupported_segments")
    if not shadow_matches:
        return CutoverGateDecision(False, "shadow_mismatch")
    return CutoverGateDecision(True, "shadow_match")
