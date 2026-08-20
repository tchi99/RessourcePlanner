from __future__ import annotations

from . import communication_ui
from .communication_excel import mark_stale_open_batches_obsolete
from .communication_queries import current_weekly_assignments
from .domain.communication_planning import snapshot_fingerprint


def install_communication_obsolescence_guard() -> None:
    """Persist stale prepared/approved lots as obsolete before Communications renders.

    This is intentionally isolated as a transitional UI guard until the broader UI
    composition refactor removes the historical installer chain.
    """
    if getattr(communication_ui, "_communication_obsolescence_guard_installed", False):
        return

    original_render = communication_ui._render_communications
    original_approve = communication_ui._approve_batch

    def _mark_current_week(self) -> None:
        selected_week = getattr(
            self,
            "_communication_week",
            communication_ui._next_week(),
        )
        assignments = current_weekly_assignments(self.repo, selected_week)
        current_fingerprint = snapshot_fingerprint(assignments)
        mark_stale_open_batches_obsolete(
            self.repo,
            selected_week,
            current_fingerprint,
        )

    def render_communications(self) -> None:
        _mark_current_week(self)
        original_render(self)

    def approve_batch(self, batch_id: str, selected_week) -> None:
        assignments = current_weekly_assignments(self.repo, selected_week)
        current_fingerprint = snapshot_fingerprint(assignments)
        mark_stale_open_batches_obsolete(
            self.repo,
            selected_week,
            current_fingerprint,
        )
        original_approve(self, batch_id, selected_week)

    communication_ui._render_communications = render_communications
    communication_ui._approve_batch = approve_batch
    communication_ui._communication_obsolescence_guard_installed = True
