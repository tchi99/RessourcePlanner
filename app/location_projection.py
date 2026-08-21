from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import nullcontext
from typing import Any


LOCATION_FIELDS = ("SiteClient", "Lieu")
APPROVED_DEMAND_STATUS = "En planification"


def _text(value: object) -> str:
    return str(value or "").strip()


def location_values(record: Mapping[str, Any] | None) -> dict[str, str]:
    """Return the persisted location projection without consulting another entity."""
    source = record or {}
    return {field: _text(source.get(field)) for field in LOCATION_FIELDS}


def has_location(record: Mapping[str, Any] | None) -> bool:
    return any(location_values(record).values())


def location_label(record: Mapping[str, Any] | None) -> str:
    """Readable location label for future operational/communication adapters."""
    values = location_values(record)
    site = values["SiteClient"]
    place = values["Lieu"]
    if site and place and site != place:
        return f"{site} · {place}"
    return place or site


def location_for_new_segment(
    values: Mapping[str, Any],
    sibling_segments: Sequence[Mapping[str, Any]],
    demand: Mapping[str, Any] | None,
) -> dict[str, str]:
    """Resolve a safe location snapshot for a newly created segment.

    Explicit values win. Otherwise an existing sibling segment is the safest source
    because it represents the last approved operational plan. The current demand may
    only be used while it is itself in the approved ``En planification`` state. This
    prevents a pending request edit from silently changing the operational location.
    """
    explicit = location_values(values)
    if any(explicit.values()):
        return explicit

    request_id = _text(values.get("NoDemande"))
    for sibling in sibling_segments:
        if request_id and _text(sibling.get("NoDemande")) != request_id:
            continue
        inherited = location_values(sibling)
        if any(inherited.values()):
            return inherited

    if demand is not None and _text(demand.get("Statut")) == APPROVED_DEMAND_STATUS:
        return location_values(demand)
    return explicit


def approved_backfill_updates(
    segment: Mapping[str, Any],
    demand: Mapping[str, Any] | None,
) -> dict[str, str]:
    """Return only missing fields that are safe to backfill from an approved demand."""
    if demand is None or _text(demand.get("Statut")) != APPROVED_DEMAND_STATUS:
        return {}
    approved = location_values(demand)
    current = location_values(segment)
    return {
        field: approved[field]
        for field in LOCATION_FIELDS
        if not current[field] and approved[field]
    }


def project_allocation_locations(
    allocation_rows: Sequence[Mapping[str, Any]],
    segment_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Copy the segment location snapshot to every persisted shift/allocation.

    The current demand is intentionally absent from this function. Segments are the
    approved ResourceRequirement projection; therefore a pending demand location can
    never leak into a shift through this persistence adapter.
    """
    locations = {
        _text(segment.get("IDSegment")): location_values(segment)
        for segment in segment_rows
        if _text(segment.get("IDSegment"))
    }
    result: list[dict[str, Any]] = []
    for row in allocation_rows:
        projected = dict(row)
        segment_id = _text(row.get("IDSegment"))
        if segment_id in locations:
            projected.update(locations[segment_id])
        result.append(projected)
    return result


def _append_once(values: list[str], field: str) -> None:
    if field not in values:
        values.append(field)


def install_location_projection() -> None:
    """Install the V1 Excel projection boundary for approved location snapshots.

    This compatibility installer is deliberately narrow: it enriches the existing
    segment storage entry points and the single allocation writer. Business decisions
    remain in the request approval workflow, while allocation persistence consumes only
    the approved segment snapshot. The wrappers can disappear when the V2 repository
    implements these projections natively.
    """
    from . import v13, v14_engine, v15_engine

    for field in LOCATION_FIELDS:
        _append_once(v13.SEGMENT_HEADERS, field)
        _append_once(v14_engine.SEGMENT_EXTRA_HEADERS, field)
        _append_once(v14_engine.ALLOCATION_HEADERS, field)

    if getattr(v13, "_location_projection_installed", False):
        return

    original_add_segment = v13.add_segment
    original_update_segment = v13.update_segment
    original_write_allocations = v15_engine._write_allocations

    def ensure_location_schema(repo: Any) -> None:
        marker = str(getattr(repo, "path", "") or "")
        if getattr(repo, "_location_projection_ready_path", None) == marker:
            return
        repo._ensure_sheet_table(v13.SEGMENT_SHEET, v13.SEGMENT_HEADERS, v13.SEGMENT_TABLE)
        repo._ensure_sheet_table(
            v14_engine.ALLOCATION_SHEET,
            v14_engine.ALLOCATION_HEADERS,
            v14_engine.ALLOCATION_TABLE,
        )
        repo.save()
        repo._location_projection_ready_path = marker

    def demand_for(repo: Any, request_id: str) -> Mapping[str, Any] | None:
        if not request_id:
            return None
        return next(
            (
                row
                for row in repo.demands()
                if _text(row.get("NoDemande")) == request_id
            ),
            None,
        )

    def backfill_approved_segments_once(repo: Any) -> None:
        marker = str(getattr(repo, "path", "") or "")
        if getattr(repo, "_location_projection_backfill_path", None) == marker:
            return
        demands = {
            _text(row.get("NoDemande")): row
            for row in repo.demands()
            if _text(row.get("NoDemande"))
        }
        updates: list[tuple[str, dict[str, str]]] = []
        for segment in v13.segment_records(repo, include_cancelled=False):
            request_id = _text(segment.get("NoDemande"))
            values = approved_backfill_updates(segment, demands.get(request_id))
            if values:
                updates.append((_text(segment.get("IDSegment")), values))

        batch_factory = getattr(repo, "batch_update", None)
        context = batch_factory("backfill approved locations") if callable(batch_factory) else nullcontext()
        with context:
            for segment_id, values in updates:
                original_update_segment(repo, segment_id, values)
        repo._location_projection_backfill_path = marker

    def add_segment_with_location(repo: Any, values: dict[str, Any]) -> str:
        ensure_location_schema(repo)
        data = dict(values)
        request_id = _text(data.get("NoDemande"))
        siblings = [
            row
            for row in v13.segment_records(repo, include_cancelled=False)
            if not request_id or _text(row.get("NoDemande")) == request_id
        ]
        data.update(
            location_for_new_segment(
                data,
                siblings,
                demand_for(repo, request_id),
            )
        )
        return original_add_segment(repo, data)

    def update_segment_with_location(
        repo: Any,
        ident: str,
        updates: dict[str, Any],
    ) -> None:
        ensure_location_schema(repo)
        data = dict(updates)
        if not any(field in data for field in LOCATION_FIELDS):
            current = next(
                (
                    row
                    for row in v13.segment_records(repo)
                    if _text(row.get("IDSegment")) == _text(ident)
                ),
                None,
            )
            request_id = _text((current or {}).get("NoDemande"))
            demand = demand_for(repo, request_id)
            if demand is not None and _text(demand.get("Statut")) == APPROVED_DEMAND_STATUS:
                data.update(location_values(demand))
        original_update_segment(repo, ident, data)

    def write_allocations_with_location(repo: Any, rows: list[dict[str, Any]]) -> None:
        ensure_location_schema(repo)
        backfill_approved_segments_once(repo)
        segments = v13.segment_records(repo, include_cancelled=True)
        original_write_allocations(repo, project_allocation_locations(rows, segments))

    v13.add_segment = add_segment_with_location
    v13.update_segment = update_segment_with_location
    v15_engine._write_allocations = write_allocations_with_location
    v13._location_projection_installed = True
