from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Generic, TypeVar


RepositoryT = TypeVar("RepositoryT")


class AllocationService(Generic[RepositoryT]):
    """Application boundary for operational allocation mutations.

    The service deliberately owns only workflow-level intent. Validation and physical
    persistence remain behind injected adapters while V1.8 still runs on Excel. This
    gives the operational UI a stable seam that can later be backed by PostgreSQL/API
    without importing NiceGUI, xlwings or historical version modules here.
    """

    def __init__(
        self,
        repository: RepositoryT,
        *,
        create_manual_record: Callable[
            [RepositoryT, str, str, Any, Any, bool, str], str
        ],
        update_manual_record: Callable[
            [RepositoryT, str, str, Any, Any, bool, str], None
        ],
        release_manual_record: Callable[[RepositoryT, str], None],
        delete_manual_record: Callable[[RepositoryT, str], None],
        assign_segment_record: Callable[
            [RepositoryT, str, str], Mapping[str, Any]
        ],
    ) -> None:
        self._repository = repository
        self._create_manual_record = create_manual_record
        self._update_manual_record = update_manual_record
        self._release_manual_record = release_manual_record
        self._delete_manual_record = delete_manual_record
        self._assign_segment_record = assign_segment_record

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
        """Create and lock a manual shift using the active storage/planning adapter."""
        segment = self._required(segment_id, "Un segment est requis pour le quart manuel.")
        tech = self._required(technician, "Un technicien est requis pour le quart manuel.")
        return self._create_manual_record(
            self._repository,
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
        """Move/reassign/update one locked shift while preserving V1 invariants."""
        identifier = self._required(
            allocation_id, "Un identifiant d'allocation est requis."
        )
        tech = self._required(technician, "Un technicien est requis pour le quart manuel.")
        self._update_manual_record(
            self._repository,
            identifier,
            tech,
            day_value,
            hours_value,
            bool(hors_horaire),
            str(note or ""),
        )

    def release_manual(self, allocation_id: str) -> None:
        """Return one locked shift to automatic planning."""
        identifier = self._required(
            allocation_id, "Un identifiant d'allocation est requis."
        )
        self._release_manual_record(self._repository, identifier)

    def delete_manual(self, allocation_id: str) -> None:
        """Delete one manual shift and let the active engine replace its remainder."""
        identifier = self._required(
            allocation_id, "Un identifiant d'allocation est requis."
        )
        self._delete_manual_record(self._repository, identifier)

    def assign_segment(self, segment_id: str, technician: str) -> dict[str, Any]:
        """Assign/reassign a segment resource and rebuild planning exactly once."""
        segment = self._required(segment_id, "Un segment est requis pour l'affectation.")
        tech = self._required(technician, "Un technicien est requis pour l'affectation.")
        return dict(self._assign_segment_record(self._repository, segment, tech))
