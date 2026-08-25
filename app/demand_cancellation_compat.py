from __future__ import annotations

from . import v18_refinements
from .excel_repository import ExcelRepository


def install_demand_cancellation_compat() -> None:
    """Preserve V1 cancellation cascade behind an explicit compatibility boundary."""

    if getattr(ExcelRepository, "_demand_cancellation_compat_installed", False):
        return

    v18_refinements._install_cancellation_cascade()
    ExcelRepository._demand_cancellation_compat_installed = True
