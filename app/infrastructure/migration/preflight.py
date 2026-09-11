from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Mapping

from .excel_cutover import (
    CutoverDiagnostic,
    CutoverExtractionReport,
    CutoverReader,
    extract_cutover_dataset,
)
from .source_links import (
    extract_demand_work_package_links,
    extract_requirement_creator_names,
)


@dataclass(frozen=True, slots=True)
class CutoverPreflight:
    report: CutoverExtractionReport
    demand_work_package_links: Mapping[str, str]
    requirement_creator_names: Mapping[str, str]

    @property
    def ok(self) -> bool:
        return self.report.ok

    def as_dict(self) -> dict[str, Any]:
        payload = self.report.as_dict()
        payload["demand_work_package_link_count"] = len(self.demand_work_package_links)
        payload["requirement_creator_count"] = len(self.requirement_creator_names)
        return payload


def _text(value: object) -> str:
    return str(value or "").strip()


def _duplicate_values(rows: tuple[dict[str, Any], ...], field: str) -> list[str]:
    values = [_text(row.get(field)) for row in rows if _text(row.get(field))]
    return sorted(value for value, count in Counter(values).items() if count > 1)


def _work_package_aliases(report: CutoverExtractionReport) -> dict[str, dict[str, Any]]:
    aliases: dict[str, dict[str, Any]] = {}
    for row in report.dataset.work_packages:
        legacy = _text(row.get("legacy_effort_id"))
        source_row = _text(row.get("source_row"))
        if legacy:
            aliases[legacy] = row
        if source_row:
            aliases[source_row] = row
    return aliases


def _extra_diagnostics(
    report: CutoverExtractionReport,
    links: Mapping[str, str],
) -> tuple[CutoverDiagnostic, ...]:
    diagnostics: list[CutoverDiagnostic] = []
    dataset = report.dataset

    for value in _duplicate_values(dataset.work_packages, "legacy_effort_id"):
        diagnostics.append(
            CutoverDiagnostic(
                "error",
                "duplicate_effort_id",
                "work_package",
                value,
                f"IDEffort dupliqué: {value}",
            )
        )
    for value in _duplicate_values(dataset.availability, "legacy_id"):
        diagnostics.append(
            CutoverDiagnostic(
                "error",
                "duplicate_availability_id",
                "availability",
                value,
                f"ID de disponibilité dupliqué: {value}",
            )
        )

    aliases = _work_package_aliases(report)
    for row in dataset.work_packages:
        identifier = _text(row.get("legacy_effort_id")) or f"row:{row.get('source_row') or '?'}"
        start = row.get("start_date")
        end = row.get("end_date")
        if start is not None and end is not None and end < start:
            diagnostics.append(
                CutoverDiagnostic(
                    "error",
                    "invalid_date_window",
                    "work_package",
                    identifier,
                    "Fenêtre de dates de l'effort invalide.",
                )
            )
        if not _text(row.get("legacy_effort_id")):
            diagnostics.append(
                CutoverDiagnostic(
                    "warning",
                    "missing_effort_id",
                    "work_package",
                    identifier,
                    "IDEffort absent; le fallback par ligne Excel sera utilisé uniquement pour le cutover.",
                )
            )

    demands = {_text(row.get("number")): row for row in dataset.demands}
    for demand_number, reference in sorted(links.items()):
        work_package = aliases.get(_text(reference))
        if work_package is None:
            diagnostics.append(
                CutoverDiagnostic(
                    "error",
                    "unknown_source_effort",
                    "demand",
                    demand_number,
                    f"SourceEffortID/SourceEffortRow introuvable: {reference}",
                )
            )
            continue
        demand = demands.get(demand_number)
        if demand is not None and _text(demand.get("project_number")) != _text(
            work_package.get("project_number")
        ):
            diagnostics.append(
                CutoverDiagnostic(
                    "error",
                    "source_effort_project_mismatch",
                    "demand",
                    demand_number,
                    "La demande et son WorkPackage source n'appartiennent pas au même projet.",
                )
            )

    for row in dataset.requirements:
        reference = _text(row.get("source_effort_id"))
        if not reference:
            continue
        work_package = aliases.get(reference)
        identifier = _text(row.get("segment_id"))
        if work_package is None:
            diagnostics.append(
                CutoverDiagnostic(
                    "error",
                    "unknown_source_effort",
                    "requirement",
                    identifier,
                    f"SourceEffortID/SourceEffortRow introuvable: {reference}",
                )
            )
            continue
        if _text(row.get("project_number")) != _text(work_package.get("project_number")):
            diagnostics.append(
                CutoverDiagnostic(
                    "error",
                    "source_effort_project_mismatch",
                    "requirement",
                    identifier,
                    "Le segment et son WorkPackage source n'appartiennent pas au même projet.",
                )
            )

    for row in dataset.history:
        if row.get("occurred_at") is None:
            diagnostics.append(
                CutoverDiagnostic(
                    "error",
                    "missing_history_timestamp",
                    "history",
                    _text(row.get("demand_number")),
                    "Horodatage historique manquant; le cutover refuse d'inventer une date.",
                )
            )

    return tuple(diagnostics)


def build_cutover_preflight(reader: CutoverReader) -> CutoverPreflight:
    base = extract_cutover_dataset(reader)
    links = extract_demand_work_package_links(reader)
    creators = extract_requirement_creator_names(reader)
    extras = _extra_diagnostics(base, links)

    # The extractor reports a missing history timestamp as a warning because extraction
    # itself can still complete. The final preflight replaces that warning with the
    # blocking cutover diagnostic above.
    retained = tuple(
        row
        for row in base.diagnostics
        if not (row.code == "missing_timestamp" and row.entity == "history")
    )
    report = CutoverExtractionReport(
        dataset=base.dataset,
        diagnostics=(*retained, *extras),
        counts=base.counts,
        hours=base.hours,
    )
    return CutoverPreflight(
        report=report,
        demand_work_package_links=dict(links),
        requirement_creator_names=dict(creators),
    )
