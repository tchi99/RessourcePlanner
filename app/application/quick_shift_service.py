from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .command_ports import AllocationCommandPort
from .repository_ports import SegmentRepositoryPort


@dataclass(frozen=True)
class QuickShiftResult:
    segment_id: str
    allocation_id: str


class QuickShiftService:
    """Create an ad-hoc segment and its locked shift as one application workflow.

    Quick Shift deliberately bypasses the workforce-request workflow. Segment and
    allocation persistence are expressed only through application ports so the same
    workflow can later run against SQL without knowing Excel or V1 modules.
    """

    ORIGIN_FIELD = "OrigineSegment"
    ORIGIN_QUICK_SHIFT = "QUICK_SHIFT"

    def __init__(
        self,
        segments: SegmentRepositoryPort,
        allocations: AllocationCommandPort,
    ) -> None:
        self._segments = segments
        self._allocations = allocations

    @staticmethod
    def _required(value: object, message: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError(message)
        return normalized

    @staticmethod
    def _positive_hours(value: object) -> float:
        try:
            hours = float(str(value).replace(",", "."))
        except (TypeError, ValueError):
            hours = 0.0
        if hours <= 0:
            raise ValueError("Les heures du quart doivent être supérieures à zéro.")
        return round(hours, 2)

    def create(
        self,
        *,
        project_number: str,
        project_name: str = "",
        technician: str,
        day_value: Any,
        hours_value: Any,
        hors_horaire: bool = False,
        note: str = "",
        description: str = "",
    ) -> QuickShiftResult:
        project = self._required(project_number, "Un projet est requis pour le quart rapide.")
        tech = self._required(technician, "Une ressource est requise pour le quart rapide.")
        if day_value in (None, ""):
            raise ValueError("La date du quart rapide est requise.")
        hours = self._positive_hours(hours_value)
        label = str(description or "").strip() or "Quart rapide"

        segment_values = {
            "NoDemande": None,
            "NumeroProjet": project,
            "NomProjet": str(project_name or "").strip() or None,
            "Technicien": tech,
            "DateDebut": day_value,
            "DateFin": day_value,
            "HeuresPrevues": hours,
            "Statut": "Planifié",
            "Description": label,
            "SourceEffortRow": None,
            "TypePlanification": "Fixe",
            "Priorite": "Normale",
            self.ORIGIN_FIELD: self.ORIGIN_QUICK_SHIFT,
        }

        segment_id = self._required(
            self._segments.create(segment_values),
            "L'identifiant du segment ad hoc",
        )
        try:
            allocation_id = self._required(
                self._allocations.create_manual(
                    segment_id,
                    tech,
                    day_value,
                    hours,
                    bool(hors_horaire),
                    str(note or "").strip(),
                ),
                "L'identifiant du quart rapide",
            )
        except Exception as exc:
            try:
                self._segments.update(segment_id, {"Statut": "Annulé"})
            except Exception as rollback_exc:
                raise RuntimeError(
                    f"Le quart rapide n'a pas été créé et le segment {segment_id} "
                    "n'a pas pu être annulé automatiquement."
                ) from rollback_exc
            raise exc

        return QuickShiftResult(
            segment_id=segment_id,
            allocation_id=allocation_id,
        )
