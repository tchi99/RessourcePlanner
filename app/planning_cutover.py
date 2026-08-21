from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable

from . import v13, v14, v14_engine, v14_fixes, v15, v15_engine, v15_refinements
from .domain.cutover_policy import (
    GUARDED_PURE_MODE,
    PURE_MODE,
    evaluate_cutover_gate,
    normalize_planning_engine_mode,
)
from .domain.planning_engine import PlanResult
from .domain.planning_snapshot import PlanningSnapshot
from .excel_repository import ExcelRepository, _date_from_any
from .planning_shadow import (
    ShadowPlanReport,
    build_planning_snapshot,
    build_shadow_report_from_snapshot,
)


LegacyRebuild = Callable[[ExcelRepository], dict[str, Any]]


def _pure_persistence_rows(
    snapshot: PlanningSnapshot,
    report: ShadowPlanReport,
) -> list[dict[str, Any]]:
    """Translate the pure result back to the current AllocationsMO persistence shape.

    Calculation and persistence deliberately reuse the same PlanningSnapshot.  This
    transitional adapter therefore does not re-read SegmentsMO, DemandesMO or
    AllocationsMO after the pure engine has calculated its result.
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
    included_ids = {
        allocation.segment_id
        for allocation in report.shadow_result.allocations
    }

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
            raise RuntimeError("Pure planning persistence could not resolve a segment from the current snapshot.")
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


def _with_cutover_metadata(
    summary: dict[str, Any],
    *,
    engine: str,
    fallback_reason: str = "",
) -> dict[str, Any]:
    result = dict(summary)
    result["planning_engine"] = engine
    result["planning_engine_fallback"] = bool(fallback_reason)
    result["planning_engine_fallback_reason"] = fallback_reason
    return result


def _pure_result_summary(result: PlanResult) -> dict[str, Any]:
    return {
        "segments": result.segment_count,
        "allocations": len([row for row in result.allocations if row.counts_as_allocated]),
        "locked_allocations": result.locked_allocation_count,
        "requested_hours": round(result.requested_hours, 2),
        "allocated_hours": round(result.allocated_hours, 2),
        "overtime_hours": round(result.overtime_hours, 2),
        "unallocated_hours": round(result.unallocated_hours, 2),
    }


def rebuild_allocations_pure(repo: ExcelRepository) -> dict[str, Any]:
    """Rebuild AllocationsMO directly from one snapshot and the pure planning engine.

    The workbook-backed planning inputs are captured once.  Calculation, diagnostics,
    locked-allocation preservation, result conversion and write recovery all reuse that
    same snapshot.  The historical engine is never executed in this path.
    """
    snapshot = build_planning_snapshot(repo)
    previous_rows = [dict(row) for row in snapshot.allocations]
    write_started = False

    try:
        report = build_shadow_report_from_snapshot(snapshot)
        if report.unsupported_segment_ids:
            raise RuntimeError(
                "Pure planning cannot rebuild while active segments are unsupported by the pure adapter."
            )

        pure_rows = _pure_persistence_rows(snapshot, report)
        write_started = True
        v15_engine._write_allocations(repo, pure_rows)
    except Exception as exc:
        if write_started:
            try:
                v15_engine._write_allocations(repo, previous_rows)
            except Exception as restore_exc:
                raise RuntimeError(
                    "Pure planning rebuild failed and the previous allocation snapshot could not be restored."
                ) from restore_exc
        print(
            "[planning-cutover] action=pure_error "
            f"error_type={type(exc).__name__} restored={str(write_started).lower()}"
        )
        raise

    result = report.shadow_result
    print(
        "[planning-cutover] action=pure_committed_direct "
        f"segments={result.segment_count} "
        f"allocations={len([row for row in result.allocations if row.counts_as_allocated])}"
    )
    return _with_cutover_metadata(_pure_result_summary(result), engine="pure")


def rebuild_allocations_guarded(
    repo: ExcelRepository,
    legacy_rebuild: LegacyRebuild,
) -> dict[str, Any]:
    """Perform a reversible guarded cutover from the legacy refined engine.

    ``guarded_pure`` is retained temporarily as a rollback/diagnostic mode while the
    direct ``pure`` mode accumulates production confidence.  Even in this transitional
    mode, each comparison/persistence phase now reuses its own captured snapshot.
    """
    legacy_summary = legacy_rebuild(repo)

    try:
        snapshot = build_planning_snapshot(repo)
        legacy_rows = [dict(row) for row in snapshot.allocations]
        report = build_shadow_report_from_snapshot(snapshot)
    except Exception as exc:
        print(f"[planning-cutover] action=fallback reason=shadow_error error_type={type(exc).__name__}")
        return _with_cutover_metadata(
            legacy_summary,
            engine="legacy",
            fallback_reason="shadow_error",
        )

    decision = evaluate_cutover_gate(
        shadow_matches=report.comparison.matches,
        unsupported_segment_count=len(report.unsupported_segment_ids),
    )
    if not decision.use_pure_engine:
        print(
            "[planning-cutover] action=fallback "
            f"reason={decision.reason} differences={len(report.comparison.differences)} "
            f"unsupported={len(report.unsupported_segment_ids)}"
        )
        return _with_cutover_metadata(
            legacy_summary,
            engine="legacy",
            fallback_reason=decision.reason,
        )

    try:
        pure_rows = _pure_persistence_rows(snapshot, report)
        v15_engine._write_allocations(repo, pure_rows)
        persisted_snapshot = build_planning_snapshot(repo)
        persisted_report = build_shadow_report_from_snapshot(persisted_snapshot)
        persisted_decision = evaluate_cutover_gate(
            shadow_matches=persisted_report.comparison.matches,
            unsupported_segment_count=len(persisted_report.unsupported_segment_ids),
        )
        if not persisted_decision.use_pure_engine:
            raise RuntimeError(f"post_write_{persisted_decision.reason}")
    except Exception as exc:
        try:
            v15_engine._write_allocations(repo, legacy_rows)
        except Exception as restore_exc:
            raise RuntimeError(
                "Pure planning cutover failed and the legacy checkpoint could not be restored."
            ) from restore_exc
        print(f"[planning-cutover] action=fallback reason=pure_write_or_validation error_type={type(exc).__name__}")
        return _with_cutover_metadata(
            legacy_summary,
            engine="legacy",
            fallback_reason="pure_write_or_validation",
        )

    print(
        "[planning-cutover] action=pure_committed "
        f"segments={report.shadow_result.segment_count} "
        f"allocations={len([row for row in report.shadow_result.allocations if row.counts_as_allocated])}"
    )
    return _with_cutover_metadata(legacy_summary, engine="pure_guarded")


def _install_rebuild_aliases(rebuild: Callable[[ExcelRepository], dict[str, Any]]) -> None:
    """Keep historical compatibility entry points pointed at one authoritative rebuild."""
    v15_refinements.rebuild_allocations_refined = rebuild
    v15_engine.rebuild_allocations = rebuild
    v14_engine.rebuild_allocations = rebuild
    v14.rebuild_allocations = rebuild
    v14_fixes.rebuild_allocations = rebuild
    v15.rebuild_allocations = rebuild


def install_planning_cutover(mode: object) -> str:
    """Install the selected runtime dispatcher after the historical installers."""
    normalized = normalize_planning_engine_mode(mode)

    if normalized == PURE_MODE:
        if getattr(v15_refinements, "_pure_engine_direct_installed", False):
            return normalized

        def pure(repo: ExcelRepository) -> dict[str, Any]:
            return rebuild_allocations_pure(repo)

        _install_rebuild_aliases(pure)
        v15_refinements._pure_engine_direct_installed = True
        print("[planning-cutover] mode=pure installed")
        return normalized

    if normalized != GUARDED_PURE_MODE:
        return normalized
    if getattr(v15_refinements, "_guarded_pure_cutover_installed", False):
        return normalized

    legacy_rebuild = v15_refinements.rebuild_allocations_refined

    def guarded(repo: ExcelRepository) -> dict[str, Any]:
        return rebuild_allocations_guarded(repo, legacy_rebuild)

    _install_rebuild_aliases(guarded)
    v15_refinements._guarded_pure_cutover_installed = True
    print("[planning-cutover] mode=guarded_pure installed")
    return normalized
