from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


PERFORMANCE_LOG_MAX_BYTES = 1_000_000
PERFORMANCE_LOG_BACKUPS = 3


@dataclass(frozen=True, slots=True)
class PerformanceSample:
    """Technical-only timing sample safe to share for diagnostics.

    The schema intentionally accepts counters and durations only. Project numbers,
    resource names, demand IDs, workbook paths and other business data do not belong
    in this object or in the performance log.
    """

    operation: str
    status: str
    total_seconds: float
    read_seconds: float = 0.0
    compute_seconds: float = 0.0
    convert_seconds: float = 0.0
    write_seconds: float = 0.0
    save_seconds: float = 0.0
    render_seconds: float = 0.0
    sheet_reads: int = 0
    range_reads: int = 0
    range_writes: int = 0
    saves: int = 0
    segment_count: int = 0
    allocation_input_count: int = 0
    allocation_output_count: int = 0
    engine: str = ""
    error_type: str = ""
    timestamp_utc: str = ""

    def normalized(self) -> "PerformanceSample":
        timestamp = self.timestamp_utc or datetime.now(timezone.utc).isoformat(timespec="seconds")
        return PerformanceSample(
            operation=str(self.operation or "unknown"),
            status=str(self.status or "unknown"),
            total_seconds=_seconds(self.total_seconds),
            read_seconds=_seconds(self.read_seconds),
            compute_seconds=_seconds(self.compute_seconds),
            convert_seconds=_seconds(self.convert_seconds),
            write_seconds=_seconds(self.write_seconds),
            save_seconds=_seconds(self.save_seconds),
            render_seconds=_seconds(self.render_seconds),
            sheet_reads=max(int(self.sheet_reads), 0),
            range_reads=max(int(self.range_reads), 0),
            range_writes=max(int(self.range_writes), 0),
            saves=max(int(self.saves), 0),
            segment_count=max(int(self.segment_count), 0),
            allocation_input_count=max(int(self.allocation_input_count), 0),
            allocation_output_count=max(int(self.allocation_output_count), 0),
            engine=str(self.engine or ""),
            error_type=str(self.error_type or ""),
            timestamp_utc=timestamp,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self.normalized())


def _seconds(value: object) -> float:
    try:
        return round(max(float(value or 0.0), 0.0), 6)
    except (TypeError, ValueError):
        return 0.0


def default_performance_log_path() -> Path:
    """Return a local technical-log location without exposing workbook data."""
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        root = Path(local_app_data) / "RessourcePlanner"
    else:
        root = Path.home() / ".resourceplanner"
    return root / "logs" / "performance.jsonl"


def _rotate_log(path: Path, max_bytes: int, backups: int) -> None:
    if max_bytes <= 0 or backups <= 0 or not path.exists():
        return
    try:
        if path.stat().st_size < max_bytes:
            return
    except OSError:
        return

    oldest = path.with_name(f"{path.name}.{backups}")
    try:
        if oldest.exists():
            oldest.unlink()
    except OSError:
        pass

    for index in range(backups - 1, 0, -1):
        source = path.with_name(f"{path.name}.{index}")
        target = path.with_name(f"{path.name}.{index + 1}")
        if not source.exists():
            continue
        try:
            source.replace(target)
        except OSError:
            pass

    try:
        path.replace(path.with_name(f"{path.name}.1"))
    except OSError:
        pass


def append_performance_sample(
    sample: PerformanceSample,
    *,
    path: Path | None = None,
    max_bytes: int = PERFORMANCE_LOG_MAX_BYTES,
    backups: int = PERFORMANCE_LOG_BACKUPS,
) -> None:
    """Append one JSONL sample. Logging must never be able to break planning."""
    target = path or default_performance_log_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        _rotate_log(target, max_bytes=max_bytes, backups=backups)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(sample.to_dict(), ensure_ascii=False, sort_keys=True))
            handle.write("\n")
    except OSError:
        return


def read_performance_samples(
    *,
    path: Path | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    target = path or default_performance_log_path()
    if limit <= 0 or not target.exists():
        return []
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    result: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            result.append(parsed)
    return result


def format_performance_report(samples: Iterable[dict[str, Any]]) -> str:
    """Format copy/paste diagnostics containing technical metrics only."""
    rows = list(samples)
    if not rows:
        return "Aucune métrique de performance disponible."

    lines = [
        "RessourcePlanner — diagnostic performance",
        "timestamp | operation | status | total | read | compute | convert | write | save | render | reads | writes | saves | segments | allocations",
    ]
    for row in rows:
        lines.append(
            "{timestamp} | {operation} | {status} | {total:.3f}s | {read:.3f}s | "
            "{compute:.3f}s | {convert:.3f}s | {write:.3f}s | {save:.3f}s | "
            "{render:.3f}s | {reads} | {writes} | {saves} | {segments} | {allocations}".format(
                timestamp=str(row.get("timestamp_utc") or ""),
                operation=str(row.get("operation") or ""),
                status=str(row.get("status") or ""),
                total=float(row.get("total_seconds") or 0.0),
                read=float(row.get("read_seconds") or 0.0),
                compute=float(row.get("compute_seconds") or 0.0),
                convert=float(row.get("convert_seconds") or 0.0),
                write=float(row.get("write_seconds") or 0.0),
                save=float(row.get("save_seconds") or 0.0),
                render=float(row.get("render_seconds") or 0.0),
                reads=int(row.get("range_reads") or 0),
                writes=int(row.get("range_writes") or 0),
                saves=int(row.get("saves") or 0),
                segments=int(row.get("segment_count") or 0),
                allocations=int(row.get("allocation_output_count") or 0),
            )
        )
        error_type = str(row.get("error_type") or "").strip()
        if error_type:
            lines.append(f"  error_type={error_type}")
    return "\n".join(lines)
