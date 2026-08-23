from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Generic, TypeVar


RepositoryT = TypeVar("RepositoryT")


class SegmentService(Generic[RepositoryT]):
    """Application boundary for operational segment mutations.

    The service owns the create/update/cancel + planning-rebuild workflow. Storage
    adapters are injected so this module remains independent from NiceGUI, Excel,
    xlwings and versioned V1.x modules.
    """

    def __init__(
        self,
        repository: RepositoryT,
        *,
        create_record: Callable[[RepositoryT, Mapping[str, Any]], str],
        update_record: Callable[[RepositoryT, str, Mapping[str, Any]], None],
        rebuild_planning: Callable[[RepositoryT], Mapping[str, Any]],
    ) -> None:
        self._repository = repository
        self._create_record = create_record
        self._update_record = update_record
        self._rebuild_planning = rebuild_planning

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
            self._create_record(self._repository, values),
            "L'identifiant du segment",
        )
        summary = self._rebuild_planning(self._repository)
        return identifier, dict(summary)

    def update(self, segment_id: str, updates: Mapping[str, Any]) -> dict[str, Any]:
        identifier = self._identifier(segment_id, "Le segment")
        self._update_record(self._repository, identifier, dict(updates))
        return dict(self._rebuild_planning(self._repository))

    def cancel(self, segment_id: str) -> dict[str, Any]:
        identifier = self._identifier(segment_id, "Le segment")
        self._update_record(self._repository, identifier, {"Statut": "Annulé"})
        return dict(self._rebuild_planning(self._repository))
