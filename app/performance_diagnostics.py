from __future__ import annotations

import json
import math
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
    auth_seconds: float = 0.0
    api_seconds: float = 0.0
    db_seconds: float = 0.0
    serialization_seconds: float = 0.0
    external_seconds: float = 0.0
    db_query_count: int = 0
    db_select_count: int = 0
    db_repeated_query_max: int = 0
    db_slow_query_count: int = 0
    db_slowest_query_seconds: float = 0.0
    db_n_plus_one_suspected: bool = False
    external_call_count: int = 0
    external_item_count: int = 0
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
            auth_seconds=_seconds(self.auth_seconds),
            api_seconds=_seconds(self.api_seconds),
            db_seconds=_seconds(self.db_seconds),
            serialization_seconds=_seconds(self.serialization_seconds),
            external_seconds=_seconds(self.external_seconds),
            db_query_count=max(int(self.db_query_count), 0),
            db_select_count=max(int(self.db_select_count), 0),
            db_repeated_query_max=max(int(self.db_repeated_query_max), 0),
            db_slow_query_count=max(int(self.db_slow_query_count), 0),
            db_slowest_query_seconds=_seconds(self.db_slowest_query_seconds),
            db_n_plus_one_suspected=bool(self.db_n_plus_one_suspected),
            external_call_count=max(int(self.external_call_count), 0),
            external_item_count=max(int(self.external_item_count), 0),
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
    backups: int = PERFORMANCE_LOG_BACKUPS,
) -> list[dict[str, Any]]:
    """Read recent technical samples across the active JSONL file and rotations."""

    target = path or default_performance_log_path()
    if limit <= 0:
        return []

    # Rotation uses .1 as the newest archived file. Read oldest -> newest so
    # slicing the tail preserves chronological order across a rotation boundary.
    candidates = [
        target.with_name(f"{target.name}.{index}")
        for index in range(max(int(backups), 0), 0, -1)
    ]
    candidates.append(target)

    lines: list[str] = []
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            lines.extend(candidate.read_text(encoding="utf-8").splitlines())
        except OSError:
            continue

    result: list[dict[str, Any]] = []
    for line in lines:
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            result.append(parsed)
    return result[-limit:]


def _percentile(values: Iterable[object], percentile: float) -> float:
    numeric = sorted(_seconds(value) for value in values)
    if not numeric:
        return 0.0
    if len(numeric) == 1:
        return numeric[0]
    rank = (len(numeric) - 1) * min(max(float(percentile), 0.0), 1.0)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return numeric[lower]
    weight = rank - lower
    return round(numeric[lower] * (1.0 - weight) + numeric[upper] * weight, 6)


def format_http_percentile_report(samples: Iterable[dict[str, Any]]) -> str:
    """Aggregate safe HTTP latency percentiles by route template."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in samples:
        operation = str(row.get("operation") or "")
        if not operation.startswith("http "):
            continue
        groups.setdefault(operation, []).append(row)
    if not groups:
        return ""

    lines = [
        "FastAPI V2 — percentiles HTTP",
        "operation | n | p50 | p95 | p99 | auth p95 | api p95 | db p95 | compute p95 | serialization p95 | external p95 | db queries p95 | n+1 suspect",
    ]
    for operation in sorted(groups):
        rows = groups[operation]
        total = [row.get("total_seconds", 0.0) for row in rows]
        lines.append(
            "{operation} | {count} | {p50:.3f}s | {p95:.3f}s | {p99:.3f}s | "
            "{auth:.3f}s | {api:.3f}s | {db:.3f}s | {compute:.3f}s | {serialization:.3f}s | "
            "{external:.3f}s | {queries:.1f} | {n_plus_one}".format(
                operation=operation,
                count=len(rows),
                p50=_percentile(total, 0.50),
                p95=_percentile(total, 0.95),
                p99=_percentile(total, 0.99),
                auth=_percentile((row.get("auth_seconds", 0.0) for row in rows), 0.95),
                api=_percentile((row.get("api_seconds", 0.0) for row in rows), 0.95),
                db=_percentile((row.get("db_seconds", 0.0) for row in rows), 0.95),
                compute=_percentile((row.get("compute_seconds", 0.0) for row in rows), 0.95),
                serialization=_percentile((row.get("serialization_seconds", 0.0) for row in rows), 0.95),
                external=_percentile((row.get("external_seconds", 0.0) for row in rows), 0.95),
                queries=_percentile((row.get("db_query_count", 0.0) for row in rows), 0.95),
                n_plus_one=sum(bool(row.get("db_n_plus_one_suspected")) for row in rows),
            )
        )
    return "\n".join(lines)


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
        if str(row.get("operation") or "").startswith("http "):
            lines.append(
                "  v2 auth={auth:.3f}s api={api:.3f}s db={db:.3f}s compute={compute:.3f}s "
                "serialization={serialization:.3f}s external={external:.3f}s db_queries={queries} "
                "repeated_max={repeated} slow={slow} n_plus_one={n_plus_one} external_calls={calls} external_items={items}".format(
                    auth=float(row.get("auth_seconds") or 0.0),
                    api=float(row.get("api_seconds") or 0.0),
                    db=float(row.get("db_seconds") or 0.0),
                    compute=float(row.get("compute_seconds") or 0.0),
                    serialization=float(row.get("serialization_seconds") or 0.0),
                    external=float(row.get("external_seconds") or 0.0),
                    queries=int(row.get("db_query_count") or 0),
                    repeated=int(row.get("db_repeated_query_max") or 0),
                    slow=int(row.get("db_slow_query_count") or 0),
                    n_plus_one=bool(row.get("db_n_plus_one_suspected")),
                    calls=int(row.get("external_call_count") or 0),
                    items=int(row.get("external_item_count") or 0),
                )
            )
        error_type = str(row.get("error_type") or "").strip()
        if error_type:
            lines.append(f"  error_type={error_type}")

    percentile_report = format_http_percentile_report(rows)
    if percentile_report:
        lines.extend(("", percentile_report))
    return "\n".join(lines)
