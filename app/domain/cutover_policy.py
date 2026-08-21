from __future__ import annotations

from dataclasses import dataclass


LEGACY_MODE = "legacy"
GUARDED_PURE_MODE = "guarded_pure"
PURE_MODE = "pure"
DEFAULT_MODE = PURE_MODE
SUPPORTED_MODES = {LEGACY_MODE, GUARDED_PURE_MODE, PURE_MODE}


@dataclass(frozen=True)
class CutoverGateDecision:
    use_pure_engine: bool
    reason: str


def normalize_planning_engine_mode(value: object) -> str:
    """Normalize the local planning-engine mode.

    New installations now default to the authoritative pure engine. An explicitly
    unknown value still falls back to legacy so a typo cannot silently select a new
    runtime path on an existing workstation.
    """
    if value is None or not str(value).strip():
        return DEFAULT_MODE
    mode = str(value).strip().lower()
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
