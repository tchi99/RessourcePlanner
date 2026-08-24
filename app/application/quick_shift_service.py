from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Generic, TypeVar


RepositoryT = TypeVar("RepositoryT")


@dataclass(frozen=True)
class QuickShiftResult:
    segment_id: str
    allocation_id: str


class QuickShiftService(Generic[RepositoryT]):
    """Create an ad-hoc segment and its locked shift as one application workflow.

    A quick shift deliberately bypasses the workforce-request workflow: it represents
    an operational decision already made. The generated segment remains the parent
    business entity so the shift can later be edited, audited and migrated to SQL
    without inventing a hidden demand.
    """

    ORIGIN_FIELD = "OrigineSegment"
    ORIGIN_QUICK_SHIFT = "QUICK_SHIFT"

    def __init__(
        self,
        repository: RepositoryT,
        *,
        create_segment_record: Callable[[RepositoryT, Mapping[str, Any]], str],
        cancel_segment_record: Callable[[RepositoryT, str], None],
        create_locked_shift_record: Callable[
            [RepositoryT, str, str, Any, Any, bool, str], str
        ],
    ) -> None:
        self._repository = repository
        self._create_segment_record = create_segment_record
        self._cancel_segment_record = cancel_segment_record
        self._create_locked_shift_record = create_locked_shift_record

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
            self._create_segment_record(self._repository, segment_values),
            "L'identifiant du segment ad hoc",
        )
        try:
            allocation_id = self._required(
                self._create_locked_shift_record(
                    self._repository,
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
                self._cancel_segment_record(self._repository, segment_id)
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
