from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date
from typing import Any, TypeVar

from .command_ports import PlanningCommandPort
from .commands import SegmentCancelCommand, SegmentCreateCommand, SegmentUpdateCommand
from .errors import (
    ApplicationError,
    ApplicationNotFoundError,
    ApplicationOperationError,
    ApplicationValidationError,
    application_error_from_exception,
)
from .repository_ports import SegmentRepositoryPort


ResultT = TypeVar("ResultT")


class SegmentService:
    """Application boundary for operational segment mutations."""

    def __init__(
        self,
        segments: SegmentRepositoryPort,
        planning: PlanningCommandPort,
    ) -> None:
        self._segments = segments
        self._planning = planning

    @staticmethod
    def _identifier(value: object) -> str:
        identifier = str(value or "").strip()
        if not identifier:
            raise ApplicationValidationError(
                "Le segment est requis.",
                code="segment_id_required",
            )
        return identifier

    @staticmethod
    def _call_adapter(
        action: Callable[[], ResultT],
        *,
        code_prefix: str,
        context: Mapping[str, Any],
    ) -> ResultT:
        try:
            return action()
        except ApplicationError:
            raise
        except Exception as exc:
            raise application_error_from_exception(
                exc,
                code_prefix=code_prefix,
                context=context,
            ) from exc

    @staticmethod
    def _validate_window(start: date | None, end: date | None) -> None:
        if start is not None and end is not None and end < start:
            raise ApplicationValidationError(
                "La date de fin ne peut pas précéder la date de début.",
                code="segment_date_window_invalid",
                context={"start": start.isoformat(), "end": end.isoformat()},
            )

    def create_command(self, command: SegmentCreateCommand) -> tuple[str, dict[str, Any]]:
        values = command.to_repository_values()
        try:
            identifier = str(self._segments.create(values) or "").strip()
        except ApplicationError:
            raise
        except Exception as exc:
            raise application_error_from_exception(
                exc,
                code_prefix="segment_create",
                context={"demand_number": command.demand_number},
            ) from exc
        if not identifier:
            raise ApplicationOperationError(
                "La création du segment n'a retourné aucun identifiant.",
                code="segment_create_id_missing",
                context={"demand_number": command.demand_number},
            )
        summary = self._call_adapter(
            self._planning.rebuild,
            code_prefix="segment_create_rebuild",
            context={"segment_id": identifier},
        )
        return identifier, dict(summary)

    def update_command(self, command: SegmentUpdateCommand) -> dict[str, Any]:
        identifier = self._identifier(command.segment_id)
        existing = self._call_adapter(
            lambda: self._segments.get(identifier),
            code_prefix="segment_lookup",
            context={"segment_id": identifier},
        )
        if existing is None:
            raise ApplicationNotFoundError(
                f"Segment {identifier} introuvable",
                code="segment_not_found",
                context={"segment_id": identifier},
            )

        values = command.to_repository_values()
        start = values.get("DateDebut", existing.start_date)
        end = values.get("DateFin", existing.end_date)
        self._validate_window(
            start if isinstance(start, date) else None,
            end if isinstance(end, date) else None,
        )

        self._call_adapter(
            lambda: self._segments.update(identifier, values),
            code_prefix="segment_update",
            context={"segment_id": identifier},
        )
        return dict(
            self._call_adapter(
                self._planning.rebuild,
                code_prefix="segment_update_rebuild",
                context={"segment_id": identifier},
            )
        )

    def cancel_command(self, command: SegmentCancelCommand) -> dict[str, Any]:
        identifier = self._identifier(command.segment_id)
        existing = self._call_adapter(
            lambda: self._segments.get(identifier),
            code_prefix="segment_lookup",
            context={"segment_id": identifier},
        )
        if existing is None:
            raise ApplicationNotFoundError(
                f"Segment {identifier} introuvable",
                code="segment_not_found",
                context={"segment_id": identifier},
            )
        self._call_adapter(
            lambda: self._segments.update(identifier, {"Statut": "Annulé"}),
            code_prefix="segment_cancel",
            context={"segment_id": identifier},
        )
        return dict(
            self._call_adapter(
                self._planning.rebuild,
                code_prefix="segment_cancel_rebuild",
                context={"segment_id": identifier},
            )
        )

    def create(self, data: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
        """Compatibility adapter for the current NiceGUI segment editor."""

        return self.create_command(SegmentCreateCommand.from_mapping(data))

    def update(self, segment_id: str, updates: Mapping[str, Any]) -> dict[str, Any]:
        return self.update_command(SegmentUpdateCommand.from_mapping(segment_id, updates))

    def cancel(self, segment_id: str) -> dict[str, Any]:
        return self.cancel_command(SegmentCancelCommand(segment_id))
