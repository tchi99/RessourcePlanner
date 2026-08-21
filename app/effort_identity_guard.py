from __future__ import annotations

from typing import Any

from . import v18
from .excel_repository import ExcelRepository


def install_effort_identity_guard() -> None:
    """Ensure rows inserted directly in Liste_Effort receive a stable identity.

    ``Liste_Effort`` remains editable directly in Excel. A row can therefore appear
    after the one-time V1.8 migration. Until repository/schema migrations replace this
    compatibility hook, every read ensures newly inserted rows have an ``IDEffort``.
    """
    if getattr(ExcelRepository, "_effort_identity_guard_installed", False):
        return

    original_efforts = ExcelRepository.efforts

    def efforts(
        self: ExcelRepository, include_closed: bool = True
    ) -> list[dict[str, Any]]:
        v18._ensure_effort_ids(self)
        return original_efforts(self, include_closed)

    ExcelRepository.efforts = efforts
    ExcelRepository._effort_identity_guard_installed = True
