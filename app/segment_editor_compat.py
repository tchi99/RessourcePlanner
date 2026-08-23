from __future__ import annotations

from typing import Any


def open_segment_editor(
    owner: Any,
    *,
    segment: dict[str, Any] | None = None,
    demand_number: str | None = None,
) -> Any:
    """Resolve the final V1.x segment editor lazily.

    The Segments page is now explicit, while the final editor implementation still
    belongs to the historical V1.5 refinement stack. Keeping that dependency in one
    compatibility adapter prevents the new page from importing a versioned module and
    gives the next extraction tranche one stable replacement point.
    """
    from . import v13

    return v13._open_segment_dialog(
        owner,
        segment=segment,
        demand_number=demand_number,
    )
