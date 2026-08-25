from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ...application.read_models import DemandReadModel
from ...application.repository_ports import DemandRepositoryPort
from ...excel_repository import ExcelRepository


class ExcelDemandRepository(DemandRepositoryPort):
    """Excel implementation of the demand persistence contract."""

    def __init__(self, repository: ExcelRepository) -> None:
        self._repository = repository

    def list(self) -> Sequence[DemandReadModel]:
        return tuple(
            DemandReadModel.from_mapping(row)
            for row in self._repository.demands()
            if str(row.get("NoDemande") or "").strip()
        )

    def get(self, number: str) -> DemandReadModel | None:
        wanted = str(number or "").strip()
        if not wanted:
            return None
        return next((row for row in self.list() if row.number == wanted), None)

    def create(self, values: Mapping[str, Any], *, submit: bool = False) -> str:
        return str(self._repository.create_demand(dict(values), submit=submit))

    def update(
        self,
        number: str,
        updates: Mapping[str, Any],
        *,
        action: str,
        comment: str = "",
    ) -> None:
        self._repository.update_demand(
            str(number),
            dict(updates),
            action=str(action),
            comment=str(comment or ""),
        )
