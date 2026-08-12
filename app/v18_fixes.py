from __future__ import annotations

from typing import Any

from . import v18
from .excel_repository import ExcelRepository


def install_v18_fixes() -> None:
    """Small compatibility guards for the V1.8 stable effort identifier layer."""
    if getattr(ExcelRepository, "_v18_fixes_installed", False):
        return

    original_efforts = ExcelRepository.efforts

    def efforts(
        self: ExcelRepository, include_closed: bool = True
    ) -> list[dict[str, Any]]:
        # Liste_Effort remains editable directly in Excel. A newly inserted row can
        # therefore appear after the one-time V1.8 schema migration. Ensure that such
        # rows receive an IDEffort before they are exposed to the rest of the app.
        v18._ensure_effort_ids(self)
        return original_efforts(self, include_closed)

    ExcelRepository.efforts = efforts
    ExcelRepository._v18_fixes_installed = True
