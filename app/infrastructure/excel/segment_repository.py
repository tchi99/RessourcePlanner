from __future__ import annotations

from collections.abc import Mapping, Sequence
from importlib import import_module
from typing import Any

from ...application.read_models import SegmentReadModel
from ...application.repository_ports import SegmentRepositoryPort


def _business_key(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        number = float(text.replace(",", "."))
        if number.is_integer():
            return str(int(number))
    except (TypeError, ValueError):
        pass
    return text


class ExcelSegmentRepository(SegmentRepositoryPort):
    """Excel implementation of the operational segment persistence contract.

    Reads and writes resolve Excel/V1 modules lazily. This keeps the application layer
    importable without xlwings/NiceGUI while preserving composed V1 write aliases such
    as approved-location projection until the Excel adapter is retired.
    """

    def __init__(self, repository: Any) -> None:
        self._repository = repository

    def _ownership_lookups(self) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
        demands = {
            str(row.get("NoDemande") or "").strip(): row
            for row in self._repository.demands()
            if str(row.get("NoDemande") or "").strip()
        }
        project_managers: dict[str, str] = {}
        try:
            projects = self._repository.projects(active_only=False)
        except Exception:
            projects = []
        for row in projects:
            number = _business_key(row.get("Numéro de Projet"))
            if not number:
                continue
            project_managers[number] = str(row.get("Chargé de projet") or "").strip()
        return demands, project_managers

    def list(self, *, include_cancelled: bool = True) -> Sequence[SegmentReadModel]:
        segment_repository = import_module("app.segment_repository")
        demands, project_managers = self._ownership_lookups()
        result: list[SegmentReadModel] = []
        for source in segment_repository.segment_records(
            self._repository,
            include_cancelled=include_cancelled,
        ):
            if not str(source.get("IDSegment") or "").strip():
                continue
            row = dict(source)
            demand = demands.get(str(row.get("NoDemande") or "").strip(), {})
            project_manager = project_managers.get(
                _business_key(row.get("NumeroProjet")),
                "",
            ) or str(demand.get("ChargeProjet") or "").strip()
            requester = str(demand.get("Demandeur") or row.get("CreePar") or "").strip()
            row["ProjectManager"] = project_manager
            row["Requester"] = requester
            result.append(SegmentReadModel.from_mapping(row))
        return tuple(result)

    def get(self, segment_id: str) -> SegmentReadModel | None:
        wanted = str(segment_id or "").strip()
        if not wanted:
            return None
        return next(
            (
                row
                for row in self.list(include_cancelled=True)
                if row.segment_id == wanted
            ),
            None,
        )

    def create(self, values: Mapping[str, Any]) -> str:
        v13 = import_module("app.v13")
        return str(v13.add_segment(self._repository, dict(values)))

    def update(self, segment_id: str, updates: Mapping[str, Any]) -> None:
        v13 = import_module("app.v13")
        v13.update_segment(self._repository, str(segment_id), dict(updates))
