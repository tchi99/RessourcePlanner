from __future__ import annotations

from typing import Any

from . import v13, v18
from .excel_repository import DEMAND_HEADERS, MASTER_SHEETS, ExcelRepository


EFFORT_ID_FIELD = v18.EFFORT_ID_FIELD
SOURCE_EFFORT_ID_FIELD = v18.SOURCE_EFFORT_ID_FIELD
EFFORT_SHEET = v18.EFFORT_SHEET


def ensure_effort_ids(repo: ExcelRepository) -> dict[int, str]:
    """Ensure stable identities for directly edited Liste_Effort rows."""

    return v18._ensure_effort_ids(repo)


def ensure_effort_identity_schema(repo: ExcelRepository) -> None:
    """Ensure the current Excel schema contains the stable effort-link fields."""

    v18.ensure_v18_schema(repo)


def install_effort_identity_compat() -> None:
    """Install only V1.8 stable-link persistence, not its historical UI routing."""

    if getattr(ExcelRepository, "_effort_identity_compat_installed", False):
        return

    if SOURCE_EFFORT_ID_FIELD not in DEMAND_HEADERS:
        DEMAND_HEADERS.append(SOURCE_EFFORT_ID_FIELD)
    if SOURCE_EFFORT_ID_FIELD not in v13.SEGMENT_HEADERS:
        v13.SEGMENT_HEADERS.append(SOURCE_EFFORT_ID_FIELD)
    MASTER_SHEETS.add(EFFORT_SHEET)

    v18._install_stable_link_wrappers()
    ExcelRepository._effort_identity_compat_installed = True
