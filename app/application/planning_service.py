from __future__ import annotations

from typing import Any

from .command_ports import PlanningCommandPort
from .commands import PlanningRebuildCommand
from .errors import ApplicationError, application_error_from_exception


class PlanningService:
    """Application boundary for authoritative planning rebuilds."""

    def __init__(self, commands: PlanningCommandPort) -> None:
        self._commands = commands

    def rebuild_command(self, _command: PlanningRebuildCommand) -> dict[str, Any]:
        try:
            return dict(self._commands.rebuild())
        except ApplicationError:
            raise
        except Exception as exc:
            raise application_error_from_exception(
                exc,
                code_prefix="planning_rebuild",
            ) from exc

    def rebuild(self) -> dict[str, Any]:
        """Compatibility adapter for the current NiceGUI entry point."""

        return self.rebuild_command(PlanningRebuildCommand())
