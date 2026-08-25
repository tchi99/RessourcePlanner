from __future__ import annotations

from typing import Any

from .command_ports import AllocationCommandPort


class AllocationService:
    """Application boundary for operational allocation mutations.

    Workflow intent lives here; persistence and planning side effects live behind
    ``AllocationCommandPort``. The service therefore has no knowledge of Excel,
    SQLAlchemy, NiceGUI or historical V1 modules.
    """

    def __init__(self, commands: AllocationCommandPort) -> None:
        self._commands = commands

    @staticmethod
    def _required(value: object, message: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError(message)
        return normalized

    def create_manual(
        self,
        segment_id: str,
        technician: str,
        day_value: Any,
        hours_value: Any,
        hors_horaire: bool = False,
        note: str = "",
    ) -> str:
        """Create and lock a manual shift through the configured command adapter."""

        segment = self._required(segment_id, "Un segment est requis pour le quart manuel.")
        tech = self._required(technician, "Un technicien est requis pour le quart manuel.")
        return self._commands.create_manual(
            segment,
            tech,
            day_value,
            hours_value,
            bool(hors_horaire),
            str(note or ""),
        )

    def update_manual(
        self,
        allocation_id: str,
        technician: str,
        day_value: Any,
        hours_value: Any,
        hors_horaire: bool = False,
        note: str = "",
    ) -> None:
        """Move/reassign/update one locked shift while preserving adapter invariants."""

        identifier = self._required(
            allocation_id, "Un identifiant d'allocation est requis."
        )
        tech = self._required(technician, "Un technicien est requis pour le quart manuel.")
        self._commands.update_manual(
            identifier,
            tech,
            day_value,
            hours_value,
            bool(hors_horaire),
            str(note or ""),
        )

    def release_manual(self, allocation_id: str) -> None:
        identifier = self._required(
            allocation_id, "Un identifiant d'allocation est requis."
        )
        self._commands.release_manual(identifier)

    def delete_manual(self, allocation_id: str) -> None:
        identifier = self._required(
            allocation_id, "Un identifiant d'allocation est requis."
        )
        self._commands.delete_manual(identifier)

    def assign_segment(self, segment_id: str, technician: str) -> dict[str, Any]:
        segment = self._required(segment_id, "Un segment est requis pour l'affectation.")
        tech = self._required(technician, "Un technicien est requis pour l'affectation.")
        return dict(self._commands.assign_segment(segment, tech))
