from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable

from . import v13, v14, v14_engine, v14_fixes, v15, v15_engine, v15_refinements
from .domain.cutover_policy import GUARDED_PURE_MODE, evaluate_cutover_gate, normalize_planning_engine_mode
from .excel_repository import ExcelRepository, _date_from_any
from .planning_shadow import ShadowPlanReport, build_shadow_report


LegacyRebuild = Callable[[ExcelRepository], dict[str, Any]]


def _pure_persistence_rows(repo: ExcelRepository, report: ShadowPlanReport) -> list[dict[str, Any]]:
    """Translate the pure result back to the current AllocationsMO persistence shape.

    This transitional adapter intentionally reuses the current V1.5 payload format so
    the cutover changes the calculation source without changing the workbook schema.
    Locked/manual rows are preserved byte-for-business-field as much as possible;
    only automatic rows are regenerated from the pure result.
    """
    with repo._lock:
        segment_rows = repo._sheet_as_records("SegmentsMO", "IDSegment")
        demand_rows = repo._sheet_as_records("DemandesMO", "NoDemande")
        allocation_rows = repo._sheet_as_records("AllocationsMO", "IDAllocation")

    segment_map = {
        str(row.get("IDSegment") or ""): row
        for row in segment_rows
        if row.get("IDSegment")
    }
    demands = {
        str(row.get("NoDemande") or ""): row
        for row in demand_rows
        if row.get("NoDemande")
    }
    included_ids = {
        allocation.segment_id
        for allocation in report.shadow_result.allocations
    }

    rows: list[dict[str, Any]] = []
    for row in allocation_rows:
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


def rebuild_allocations_guarded(
    repo: ExcelRepository,
    legacy_rebuild: LegacyRebuild,
) -> dict[str, Any]:
    """Perform a reversible guarded cutover from the legacy refined engine.

    Safety sequence:
    1. run and persist the known-good legacy plan;
    2. compare it to the pure engine without writes;
    3. only when the comparison is complete and exact, persist the pure equivalent;
    4. validate the persisted pure plan again;
    5. restore the legacy rows if pure persistence or validation fails.

    During this transition the extra legacy write is intentional. It provides a
    recoverable checkpoint until the pure engine has accumulated enough production
    confidence to become authoritative directly.
    """
    legacy_summary = legacy_rebuild(repo)
    legacy_rows = v15_engine.allocation_records(repo)

    try:
        report = build_shadow_report(repo)
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
        pure_rows = _pure_persistence_rows(repo, report)
        v15_engine._write_allocations(repo, pure_rows)
        persisted_report = build_shadow_report(repo)
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


def install_planning_cutover(mode: object) -> str:
    """Install the guarded runtime dispatcher after the historical installers."""
    normalized = normalize_planning_engine_mode(mode)
    if normalized != GUARDED_PURE_MODE:
        return normalized
    if getattr(v15_refinements, "_guarded_pure_cutover_installed", False):
        return normalized

    legacy_rebuild = v15_refinements.rebuild_allocations_refined

    def guarded(repo: ExcelRepository) -> dict[str, Any]:
        return rebuild_allocations_guarded(repo, legacy_rebuild)

    # v15_refinements functions resolve this module global at call time, including the
    # approval and UI recalculate wrappers created during install_v15_refinements().
    v15_refinements.rebuild_allocations_refined = guarded

    # Keep the historical module aliases coherent for callers that use V1.4/V1.5
    # compatibility entry points.
    v15_engine.rebuild_allocations = guarded
    v14_engine.rebuild_allocations = guarded
    v14.rebuild_allocations = guarded
    v14_fixes.rebuild_allocations = guarded
    v15.rebuild_allocations = guarded

    v15_refinements._guarded_pure_cutover_installed = True
    print("[planning-cutover] mode=guarded_pure installed")
    return normalized
