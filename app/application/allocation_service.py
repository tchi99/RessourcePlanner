from __future__ import annotations

from datetime import date
from typing import Any

from .command_ports import AllocationCommandPort
from .commands import (
    ManualAllocationCreateCommand,
    ManualAllocationDeleteCommand,
    ManualAllocationReleaseCommand,
    ManualAllocationUpdateCommand,
    SegmentAssignCommand,
)
from .errors import ApplicationValidationError, call_application_port


class AllocationService:
    """Application boundary for operational allocation mutations."""

    def __init__(self, commands: AllocationCommandPort) -> None:
        self._commands = commands

    @staticmethod
    def _required(value: object, *, code: str, message: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ApplicationValidationError(message, code=code)
        return normalized

    @staticmethod
    def _positive_hours(value: object) -> float:
        try:
            hours = float(value)
        except (TypeError, ValueError) as exc:
            raise ApplicationValidationError(
                "Les heures du quart doivent être numériques.",
                code="allocation_hours_invalid",
                context={"value": value},
            ) from exc
        if hours <= 0:
            raise ApplicationValidationError(
                "Les heures du quart doivent être supérieures à zéro.",
                code="allocation_hours_invalid",
                context={"value": hours},
            )
        return round(hours, 2)

    @staticmethod
    def _day(value: object) -> date:
        if not isinstance(value, date):
            raise ApplicationValidationError(
                "La date du quart est requise.",
                code="allocation_day_invalid",
                context={"value": value},
            )
        return value

    def create_manual_command(self, command: ManualAllocationCreateCommand) -> str:
        segment = self._required(
            command.segment_id,
            code="allocation_segment_required",
            message="Un segment est requis pour le quart manuel.",
        )
        tech = self._required(
            command.technician,
            code="allocation_resource_required",
            message="Un technicien est requis pour le quart manuel.",
        )
        day = self._day(command.day)
        hours = self._positive_hours(command.hours)
        return call_application_port(
            lambda: self._commands.create_manual(
                segment,
                tech,
                day,
                hours,
                bool(command.outside_standard_hours),
                str(command.note or ""),
            ),
            code_prefix="allocation_create",
            context={"segment_id": segment, "technician": tech},
        )

    def update_manual_command(self, command: ManualAllocationUpdateCommand) -> None:
        identifier = self._required(
            command.allocation_id,
            code="allocation_id_required",
            message="Un identifiant d'allocation est requis.",
        )
        tech = self._required(
            command.technician,
            code="allocation_resource_required",
            message="Un technicien est requis pour le quart manuel.",
        )
        day = self._day(command.day)
        hours = self._positive_hours(command.hours)
        call_application_port(
            lambda: self._commands.update_manual(
                identifier,
                tech,
                day,
                hours,
                bool(command.outside_standard_hours),
                str(command.note or ""),
            ),
            code_prefix="allocation_update",
            context={"allocation_id": identifier, "technician": tech},
        )

    def release_manual_command(self, command: ManualAllocationReleaseCommand) -> None:
        identifier = self._required(
            command.allocation_id,
            code="allocation_id_required",
            message="Un identifiant d'allocation est requis.",
        )
        call_application_port(
            lambda: self._commands.release_manual(identifier),
            code_prefix="allocation_release",
            context={"allocation_id": identifier},
        )

    def delete_manual_command(self, command: ManualAllocationDeleteCommand) -> None:
        identifier = self._required(
            command.allocation_id,
            code="allocation_id_required",
            message="Un identifiant d'allocation est requis.",
        )
        call_application_port(
            lambda: self._commands.delete_manual(identifier),
            code_prefix="allocation_delete",
            context={"allocation_id": identifier},
        )

    def assign_segment_command(self, command: SegmentAssignCommand) -> dict[str, Any]:
        segment = self._required(
            command.segment_id,
            code="allocation_segment_required",
            message="Un segment est requis pour l'affectation.",
        )
        tech = self._required(
            command.technician,
            code="allocation_resource_required",
            message="Un technicien est requis pour l'affectation.",
        )
        return dict(
            call_application_port(
                lambda: self._commands.assign_segment(segment, tech),
                code_prefix="segment_assignment",
                context={"segment_id": segment, "technician": tech},
            )
        )

    def create_manual(
        self,
        segment_id: str,
        technician: str,
        day_value: Any,
        hours_value: Any,
        hors_horaire: bool = False,
        note: str = "",
    ) -> str:
        """Compatibility adapter for current NiceGUI/V1 callers."""

        return self.create_manual_command(
            ManualAllocationCreateCommand.from_values(
                segment_id,
                technician,
                day_value,
                hours_value,
                hors_horaire,
                note,
            )
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
        self.update_manual_command(
            ManualAllocationUpdateCommand.from_values(
                allocation_id,
                technician,
                day_value,
                hours_value,
                hors_horaire,
                note,
            )
        )

    def release_manual(self, allocation_id: str) -> None:
        self.release_manual_command(ManualAllocationReleaseCommand(allocation_id))

    def delete_manual(self, allocation_id: str) -> None:
        self.delete_manual_command(ManualAllocationDeleteCommand(allocation_id))

    def assign_segment(self, segment_id: str, technician: str) -> dict[str, Any]:
        return self.assign_segment_command(SegmentAssignCommand(segment_id, technician))
