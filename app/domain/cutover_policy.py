from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CutoverGateDecision:
    use_pure_engine: bool
    reason: str


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
