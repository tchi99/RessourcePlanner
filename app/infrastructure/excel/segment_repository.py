from __future__ import annotations

from collections.abc import Mapping, Sequence
from importlib import import_module
from typing import Any

from ...application.read_models import SegmentReadModel
from ...application.repository_ports import SegmentRepositoryPort
from ...excel_repository import ExcelRepository
from ...segment_repository import segment_records


class ExcelSegmentRepository(SegmentRepositoryPort):
    """Excel implementation of the operational segment persistence contract.

    Reads use the stable ``segment_repository`` boundary. Writes resolve the composed
    V1 alias lazily because compatibility installers still enrich those entry points
    (for example approved location projection) until the Excel adapter is retired.
    """

    def __init__(self, repository: ExcelRepository) -> None:
        self._repository = repository

    def list(self, *, include_cancelled: bool = True) -> Sequence[SegmentReadModel]:
        return tuple(
            SegmentReadModel.from_mapping(row)
            for row in segment_records(
                self._repository,
                include_cancelled=include_cancelled,
            )
            if str(row.get("IDSegment") or "").strip()
        )

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
