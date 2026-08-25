from __future__ import annotations

from typing import Any

from .command_ports import PlanningCommandPort
from .commands import PlanningRebuildCommand
from .errors import call_application_port


class PlanningService:
    """Application boundary for authoritative planning rebuilds."""

    def __init__(self, commands: PlanningCommandPort) -> None:
        self._commands = commands

    def rebuild_command(self, _command: PlanningRebuildCommand) -> dict[str, Any]:
        return dict(
            call_application_port(
                self._commands.rebuild,
                code_prefix="planning_rebuild",
            )
        )

    def rebuild(self) -> dict[str, Any]:
        """Compatibility adapter for the current NiceGUI entry point."""

        return self.rebuild_command(PlanningRebuildCommand())
