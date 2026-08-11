from __future__ import annotations

from . import v13
from . import v14
from . import v14_engine
from .excel_repository import ExcelRepository


def install_v14_runtime() -> None:
    if getattr(v14, "_v14_runtime_installed", False):
        return

    # Les pages Segments et Planification sont appelées par des closures V1.3;
    # on remplace donc aussi les fonctions globales résolues au moment du rendu.
    v13._render_segments = v14._render_segments_v14
    v13._render_operational_planning = v14._render_operational_planning_v14

    # Évite de reformater/autofitter les feuilles à chaque rafraîchissement UI.
    original_ensure = v14_engine.ensure_v14_sheets

    def cached_ensure(repo: ExcelRepository) -> None:
        marker = str(repo.path or "")
        if getattr(repo, "_v14_ready_path", None) == marker:
            return
        original_ensure(repo)
        repo._v14_ready_path = marker

    v14_engine.ensure_v14_sheets = cached_ensure
    v14.ensure_v14_sheets = cached_ensure

    v14._v14_runtime_installed = True
