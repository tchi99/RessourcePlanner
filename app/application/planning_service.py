from __future__ import annotations

from typing import Any

from .command_ports import PlanningCommandPort


class PlanningService:
    """Application boundary for authoritative planning rebuilds.

    The service depends only on ``PlanningCommandPort``. NiceGUI, Excel, xlwings and
    the concrete planning engine belong to the adapter/composition layers.
    """

    def __init__(self, commands: PlanningCommandPort) -> None:
        self._commands = commands

    def rebuild(self) -> dict[str, Any]:
        """Recalculate and persist the authoritative operational plan."""

        return dict(self._commands.rebuild())
