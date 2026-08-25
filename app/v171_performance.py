from __future__ import annotations

"""Compatibility shim for the extracted runtime performance adapter."""

from .runtime_performance_compat import (
    AVAILABILITY_CACHE_SECONDS,
    _install_availability_optimizations,
    _install_repository_batching,
    _install_resource_write_optimizations,
    _install_schema_ensure_optimizations,
    _invalidate_runtime_caches,
    _manual_order_dialog_fast,
    _move_manual_resource_fast,
    _order_number,
    _path_marker,
    _restore_excel_ui,
    _suspend_excel_ui,
    _write_order_column,
    install_runtime_performance_compat,
)


def install_v171_performance() -> None:
    """Backward-compatible installer alias."""

    install_runtime_performance_compat()
