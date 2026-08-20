from __future__ import annotations

from typing import Iterable, Sequence


def partition_unavailable_recipients(
    missing_contact_ids: Sequence[str],
    inactive_contact_ids: Iterable[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split unavailable recipients into blockers and non-blocking inactive warnings.

    Active/missing recipients remain blockers because the coordinator must provide an
    address before preparing the communication batch. Recipients explicitly marked
    inactive are intentionally suppressed from the batch and returned as warnings.
    """
    inactive = {str(value or "").strip() for value in inactive_contact_ids}
    missing = {str(value or "").strip() for value in missing_contact_ids}
    missing.discard("")
    inactive.discard("")

    suppressed = tuple(sorted(missing & inactive))
    blockers = tuple(sorted(missing - inactive))
    return blockers, suppressed
