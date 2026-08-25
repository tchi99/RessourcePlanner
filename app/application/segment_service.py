from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .command_ports import PlanningCommandPort
from .repository_ports import SegmentRepositoryPort


class SegmentService:
    """Application boundary for operational segment mutations.

    Segment persistence and planning rebuild are explicit ports, so this service is
    directly reusable by FastAPI or SQL adapters without repository-context callbacks.
    """

    def __init__(
        self,
        segments: SegmentRepositoryPort,
        planning: PlanningCommandPort,
    ) -> None:
        self._segments = segments
        self._planning = planning

    @staticmethod
    def _identifier(value: object, label: str) -> str:
        identifier = str(value or "").strip()
        if not identifier:
            raise ValueError(f"{label} est requis.")
        return identifier

    def create(self, data: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
        values = dict(data)
        self._identifier(values.get("NoDemande"), "La demande")
        identifier = self._identifier(
            self._segments.create(values),
            "L'identifiant du segment",
        )
        return identifier, dict(self._planning.rebuild())

    def update(self, segment_id: str, updates: Mapping[str, Any]) -> dict[str, Any]:
        identifier = self._identifier(segment_id, "Le segment")
        self._segments.update(identifier, dict(updates))
        return dict(self._planning.rebuild())

    def cancel(self, segment_id: str) -> dict[str, Any]:
        identifier = self._identifier(segment_id, "Le segment")
        self._segments.update(identifier, {"Statut": "Annulé"})
        return dict(self._planning.rebuild())
