from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from .config import BASE_DIR


VALIDATION_PATH = BASE_DIR / "planning_pure_validation.json"
SCHEMA_VERSION = 1


def _empty_state() -> dict[str, Any]:
    return {
        "schema": SCHEMA_VERSION,
        "pure_success_count": 0,
        "pure_error_count": 0,
        "consecutive_pure_successes": 0,
        "first_pure_success_at": "",
        "last_pure_success_at": "",
        "last_pure_error_at": "",
        "last_error_type": "",
        "last_total_seconds": 0.0,
        "last_segment_count": 0,
        "last_allocation_output_count": 0,
    }


def load_validation_state(path: Path | None = None) -> dict[str, Any]:
    target = path or VALIDATION_PATH
    state = _empty_state()
    if not target.exists():
        return state
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return state
    if not isinstance(raw, dict):
        return state
    for key in state:
        if key in raw:
            state[key] = raw[key]
    state["schema"] = SCHEMA_VERSION
    return state


def _write_state(state: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(dict(state), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def record_pure_cycle(
    sample: Mapping[str, Any],
    *,
    path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Persist a technical-only success/error counter for real pure rebuilds.

    No project, technician, request, location or workbook data is stored. This journal
    is evidence that the direct pure path actually ran; it does not replace functional
    validation of approval/reapproval/manual-shift scenarios required by #56.
    """
    if str(sample.get("engine") or "").strip().lower() != "pure":
        return load_validation_state(path)

    target = path or VALIDATION_PATH
    state = load_validation_state(target)
    stamp = (now or datetime.now()).isoformat(timespec="seconds")
    status = str(sample.get("status") or "").strip().lower()

    try:
        state["last_total_seconds"] = round(float(sample.get("total_seconds") or 0.0), 3)
    except (TypeError, ValueError):
        state["last_total_seconds"] = 0.0
    try:
        state["last_segment_count"] = int(sample.get("segment_count") or 0)
    except (TypeError, ValueError):
        state["last_segment_count"] = 0
    try:
        state["last_allocation_output_count"] = int(
            sample.get("allocation_output_count") or 0
        )
    except (TypeError, ValueError):
        state["last_allocation_output_count"] = 0

    if status == "success":
        state["pure_success_count"] = int(state.get("pure_success_count") or 0) + 1
        state["consecutive_pure_successes"] = int(
            state.get("consecutive_pure_successes") or 0
        ) + 1
        if not str(state.get("first_pure_success_at") or ""):
            state["first_pure_success_at"] = stamp
        state["last_pure_success_at"] = stamp
    else:
        state["pure_error_count"] = int(state.get("pure_error_count") or 0) + 1
        state["consecutive_pure_successes"] = 0
        state["last_pure_error_at"] = stamp
        state["last_error_type"] = str(sample.get("error_type") or "")

    try:
        _write_state(state, target)
    except Exception as exc:
        # Validation telemetry must never make planning fail.
        print(f"[planning-validation] journal_write_error={type(exc).__name__}")
    return state
