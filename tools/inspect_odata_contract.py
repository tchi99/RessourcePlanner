from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
import sys

from app.infrastructure.acumatica.odata_atom import (
    ODataAtomFeed,
    ODataAtomFeedError,
    ODataAtomProperty,
    parse_atom_feed,
)


@dataclass(slots=True)
class _FieldSummary:
    explicit_types: set[str] = field(default_factory=set)
    implicit_string: bool = False
    null_observed: bool = False
    preserve_space_observed: bool = False
    present_in_entries: int = 0


def _type_label(summary: _FieldSummary) -> str:
    labels = sorted(summary.explicit_types)
    if summary.implicit_string:
        labels.append("string (implicit)")
    return " / ".join(labels) if labels else "unknown"


def _field_summaries(feed: ODataAtomFeed) -> dict[str, _FieldSummary]:
    summaries: dict[str, _FieldSummary] = {}
    for entry in feed.entries:
        seen: set[str] = set()
        for prop in entry.properties:
            summary = summaries.setdefault(prop.name, _FieldSummary())
            if prop.edm_type:
                summary.explicit_types.add(prop.edm_type)
            else:
                summary.implicit_string = True
            summary.null_observed = summary.null_observed or prop.is_null
            summary.preserve_space_observed = (
                summary.preserve_space_observed or prop.preserves_space
            )
            if prop.name not in seen:
                summary.present_in_entries += 1
                seen.add(prop.name)
    return summaries


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def render_contract_report(feed: ODataAtomFeed) -> str:
    """Render structural OData metadata only; property values are never included."""

    lines = [
        "Feed format: Atom/XML",
        f"Entries: {len(feed.entries)}",
        f"Title: {feed.title or 'not observed'}",
    ]
    entities = feed.entity_types
    lines.append(
        "Entity: " + (", ".join(entities) if entities else "not observed")
    )

    lines.append("Namespaces:")
    if feed.namespaces:
        for prefix, uri in feed.namespaces:
            label = prefix or "(default)"
            lines.append(f"- {label}: {uri}")
    else:
        lines.append("- none observed")

    summaries = _field_summaries(feed)
    lines.append("Fields:")
    if not summaries:
        lines.append("- none")
    for name in sorted(summaries):
        summary = summaries[name]
        missing = summary.present_in_entries < len(feed.entries)
        lines.append(
            f"- {name}: {_type_label(summary)}; "
            f"m:null={_yes_no(summary.null_observed)}; "
            f"missing={_yes_no(missing)}; "
            f"xml:space=preserve={_yes_no(summary.preserve_space_observed)}"
        )

    all_properties: tuple[ODataAtomProperty, ...] = tuple(
        prop for entry in feed.entries for prop in entry.properties
    )
    lines.extend(
        [
            "Observed:",
            f"- m:null: {_yes_no(any(prop.is_null for prop in all_properties))}",
            "- xml:space=preserve: "
            + _yes_no(any(prop.preserves_space for prop in all_properties)),
            f"- Atom self links: {_yes_no(feed.has_self_links)}",
        ]
    )
    return "\n".join(lines)


def inspect_odata_contract(xml_payload: bytes | str) -> str:
    return render_contract_report(parse_atom_feed(xml_payload))


def inspect_odata_file(path: Path) -> str:
    return inspect_odata_contract(path.read_bytes())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect an anonymized Atom/XML OData sample locally and print only "
            "structural contract metadata. No network access is performed."
        )
    )
    parser.add_argument("sample", type=Path, help="Local anonymized Atom/XML sample")
    args = parser.parse_args(argv)

    try:
        report = inspect_odata_file(args.sample)
    except ODataAtomFeedError as exc:
        print(
            f"Contract inspection failed: {exc.reason}",
            file=sys.stderr,
        )
        return 2
    except OSError:
        print("Contract inspection failed: unable_to_read_file", file=sys.stderr)
        return 2

    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
