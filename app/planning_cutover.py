from __future__ import annotations

import time
from datetime import date, datetime
from typing import Any, Callable

from . import v13, v14, v14_engine, v14_fixes, v15, v15_engine, v15_refinements
from .domain.planning_engine import PlanResult
from .domain.planning_snapshot import PlanningSnapshot
from .excel_repository import ExcelRepository, _date_from_any
from .performance_diagnostics import PerformanceSample, append_performance_sample
from .planning_shadow import ShadowPlanReport, build_planning_snapshot, build_shadow_report_from_snapshot


def _pure_persistence_rows(
    snapshot: PlanningSnapshot,
    report: ShadowPlanReport,
) -> list[dict[str, Any]]:
    """Translate the pure result back to the current AllocationsMO persistence shape.

    Calculation and persistence reuse the same PlanningSnapshot. The adapter never
    re-reads SegmentsMO, DemandesMO or AllocationsMO after the pure calculation.
    """
    segment_map = {
        str(row.get("IDSegment") or ""): row
        for row in snapshot.segments
        if row.get("IDSegment")
    }
    demands = {
        str(row.get("NoDemande") or ""): row
        for row in snapshot.demands
        if row.get("NoDemande")
    }
    included_ids = {allocation.segment_id for allocation in report.shadow_result.allocations}

    rows: list[dict[str, Any]] = []
    for row in snapshot.allocations:
        if not v15_engine._truthy(row.get("Verrouillee")):
            continue
        segment_id = str(row.get("IDSegment") or "")
        if segment_id not in included_ids:
            continue
        day = _date_from_any(row.get("Date"))
        technician = str(row.get("Technicien") or "").strip()
        hours = v13._number(row.get("Heures"))
        if not day or not technician or hours <= 0:
            continue
        clean = dict(row)
        clean["Date"] = day
        clean["Heures"] = round(hours, 2)
        clean["Verrouillee"] = "Oui"
        clean["HorsHoraire"] = "Oui" if v15_engine._truthy(row.get("HorsHoraire")) else "Non"
        rows.append(clean)

    generation = datetime.now()
    sequence = 0
    for allocation in report.shadow_result.allocations:
        if allocation.locked:
            continue
        segment = segment_map.get(allocation.segment_id)
        if not segment:
            raise RuntimeError(
                "Pure planning persistence could not resolve a segment from the current snapshot."
            )
        sequence += 1
        competence = v14_engine.segment_competence(segment, demands)
        priority = v14_engine.segment_priority(segment, demands)
        if not allocation.counts_as_allocated:
            hors_horaire = "Requis"
            note = "Capacité standard insuffisante — quart hors horaire à confirmer"
        elif allocation.outside_schedule:
            hors_horaire = "Oui"
            note = "Hors horaire autorisé au niveau du segment"
        else:
            hors_horaire = "Non"
            note = ""
        rows.append(
            v15_refinements._auto_payload(
                segment,
                allocation.day,
                allocation.hours,
                allocation.allocation_type,
                competence,
                priority,
                sequence,
                generation,
                hors_horaire=hors_horaire,
                note=note,
            )
        )

    rows.sort(
        key=lambda row: (
            str(row.get("Technicien") or ""),
            _date_from_any(row.get("Date")) or date.max,
            0 if v15_engine._truthy(row.get("Verrouillee")) else 1,
            str(row.get("TypeAllocation") or ""),
            str(row.get("IDSegment") or ""),
        )
    )
    return rows


def _pure_result_summary(result: PlanResult) -> dict[str, Any]:
    return {
        "segments": result.segment_count,
        "allocations": len([row for row in result.allocations if row.counts_as_allocated]),
        "locked_allocations": result.locked_allocation_count,
        "requested_hours": round(result.requested_hours, 2),
        "allocated_hours": round(result.allocated_hours, 2),
        "overtime_hours": round(result.overtime_hours, 2),
        "unallocated_hours": round(result.unallocated_hours, 2),
        "planning_engine": "pure",
    }


def _repo_performance_snapshot(repo: ExcelRepository) -> dict[str, Any]:
    method = getattr(repo, "performance_snapshot", None)
    if not callable(method):
        return {}
    try:
        value = method()
    except Exception:
        return {}
    return dict(value) if isinstance(value, dict) else {}


def _save_metrics_delta(
    before: dict[str, Any],
    after: dict[str, Any],
) -> tuple[int, float]:
    before_count = int(before.get("actual_save_count") or 0)
    after_count = int(after.get("actual_save_count") or 0)
    saves = max(after_count - before_count, 0)
    if saves <= 0:
        return 0, 0.0
    return saves, max(float(after.get("last_save_seconds") or 0.0), 0.0)


def _publish_planning_performance(repo: ExcelRepository, sample: PerformanceSample) -> dict[str, Any]:
    data = sample.to_dict()
    repo._last_planning_performance = dict(data)
    append_performance_sample(sample)
    print(
        "[performance] operation=planning_rebuild "
        f"status={data['status']} total={data['total_seconds']:.3f}s "
        f"read={data['read_seconds']:.3f}s compute={data['compute_seconds']:.3f}s "
        f"convert={data['convert_seconds']:.3f}s write={data['write_seconds']:.3f}s "
        f"save={data['save_seconds']:.3f}s"
    )
    return data


def rebuild_allocations_pure(repo: ExcelRepository) -> dict[str, Any]:
    """Rebuild AllocationsMO directly from one snapshot and the pure planning engine."""
    operation_started = time.perf_counter()
    read_seconds = 0.0
    compute_seconds = 0.0
    convert_seconds = 0.0
    write_total_seconds = 0.0
    save_seconds = 0.0
    save_count = 0
    snapshot: PlanningSnapshot | None = None
    pure_rows: list[dict[str, Any]] = []
    write_started = False
    save_before = _repo_performance_snapshot(repo)

    try:
        phase_started = time.perf_counter()
        snapshot = build_planning_snapshot(repo)
        read_seconds = time.perf_counter() - phase_started

        phase_started = time.perf_counter()
        report = build_shadow_report_from_snapshot(snapshot)
        compute_seconds = time.perf_counter() - phase_started
        if report.unsupported_segment_ids:
            raise RuntimeError(
                "Pure planning cannot rebuild while active segments are unsupported by the pure adapter."
            )

        phase_started = time.perf_counter()
        pure_rows = _pure_persistence_rows(snapshot, report)
        convert_seconds = time.perf_counter() - phase_started

        phase_started = time.perf_counter()
        write_started = True
        v15_engine._write_allocations(repo, pure_rows)
        write_total_seconds = time.perf_counter() - phase_started
        save_after = _repo_performance_snapshot(repo)
        save_count, save_seconds = _save_metrics_delta(save_before, save_after)
    except Exception as exc:
        if write_started and snapshot is not None:
            try:
                v15_engine._write_allocations(repo, [dict(row) for row in snapshot.allocations])
            except Exception as restore_exc:
                raise RuntimeError(
                    "Pure planning rebuild failed and the previous allocation snapshot could not be restored."
                ) from restore_exc

        sample = PerformanceSample(
            operation="planning_rebuild",
            status="error",
            total_seconds=time.perf_counter() - operation_started,
            read_seconds=read_seconds,
            compute_seconds=compute_seconds,
            convert_seconds=convert_seconds,
            write_seconds=max(write_total_seconds - save_seconds, 0.0),
            save_seconds=save_seconds,
            sheet_reads=5 if snapshot is not None else 0,
            range_reads=5 if snapshot is not None else 0,
            range_writes=(2 if pure_rows else 1) if write_started else 0,
            saves=save_count,
            segment_count=len(snapshot.segments) if snapshot is not None else 0,
            allocation_input_count=len(snapshot.allocations) if snapshot is not None else 0,
            allocation_output_count=len(pure_rows),
            engine="pure",
            error_type=type(exc).__name__,
        )
        _publish_planning_performance(repo, sample)
        print(
            "[planning-engine] action=pure_error "
            f"error_type={type(exc).__name__} restored={str(write_started).lower()}"
        )
        raise

    result = report.shadow_result
    sample = PerformanceSample(
        operation="planning_rebuild",
        status="success",
        total_seconds=time.perf_counter() - operation_started,
        read_seconds=read_seconds,
        compute_seconds=compute_seconds,
        convert_seconds=convert_seconds,
        write_seconds=max(write_total_seconds - save_seconds, 0.0),
        save_seconds=save_seconds,
        sheet_reads=5,
        range_reads=5,
        range_writes=2 if pure_rows else 1,
        saves=save_count,
        segment_count=result.segment_count,
        allocation_input_count=len(snapshot.allocations),
        allocation_output_count=len(pure_rows),
        engine="pure",
    )
    performance = _publish_planning_performance(repo, sample)

    print(
        "[planning-engine] action=pure_committed "
        f"segments={result.segment_count} "
        f"allocations={len([row for row in result.allocations if row.counts_as_allocated])}"
    )
    summary = _pure_result_summary(result)
    summary["performance"] = performance
    return summary


def _install_rebuild_aliases(rebuild: Callable[[ExcelRepository], dict[str, Any]]) -> None:
    """Point all transitional V1 entry points at the sole authoritative engine."""
    v15_refinements.rebuild_allocations_refined = rebuild
    v15_engine.rebuild_allocations = rebuild
    v14_engine.rebuild_allocations = rebuild
    v14.rebuild_allocations = rebuild
    v14_fixes.rebuild_allocations = rebuild
    v15.rebuild_allocations = rebuild


def install_planning_engine() -> str:
    """Install the pure engine as the only production planning runtime."""
    if getattr(v15_refinements, "_pure_engine_direct_installed", False):
        return "pure"

    _install_rebuild_aliases(rebuild_allocations_pure)
    v15_refinements._pure_engine_direct_installed = True
    print("[planning-engine] mode=pure installed")
    return "pure"
