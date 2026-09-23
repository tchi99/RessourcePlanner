from __future__ import annotations

from .command_ports import CompositeAllocationCommandPort
from .commands import AllocationDuplicateCommand, AllocationSplitCommand
from .errors import ApplicationOperationError, call_application_port
from .results import CompositeAllocationMutationResult


class CompositeAllocationService:
    """Application boundary for atomic split/duplicate shift mutations."""

    def __init__(self, commands: CompositeAllocationCommandPort) -> None:
        self._commands = commands

    @staticmethod
    def _available(commands: CompositeAllocationCommandPort | None) -> CompositeAllocationCommandPort:
        if commands is None:
            raise ApplicationOperationError(
                "Les commandes composites de quart ne sont pas configurées.",
                code="composite_allocation_commands_unavailable",
            )
        return commands

    def split_command(
        self,
        command: AllocationSplitCommand,
    ) -> CompositeAllocationMutationResult:
        result = call_application_port(
            lambda: self._commands.split(command),
            code_prefix="allocation_split",
            context={"allocation_id": command.allocation_id},
        )
        return CompositeAllocationMutationResult.from_mapping(result)

    def duplicate_command(
        self,
        command: AllocationDuplicateCommand,
    ) -> CompositeAllocationMutationResult:
        result = call_application_port(
            lambda: self._commands.duplicate(command),
            code_prefix="allocation_duplicate",
            context={"allocation_id": command.allocation_id},
        )
        return CompositeAllocationMutationResult.from_mapping(result)
