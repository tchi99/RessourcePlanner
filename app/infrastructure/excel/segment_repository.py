from __future__ import annotations

from collections.abc import Mapping, Sequence
from importlib import import_module
from typing import Any

from ...application.read_models import SegmentReadModel
from ...application.repository_ports import SegmentRepositoryPort


class ExcelSegmentRepository(SegmentRepositoryPort):
    """Excel implementation of the operational segment persistence contract.

    Reads and writes resolve Excel/V1 modules lazily. This keeps the application layer
    importable without xlwings/NiceGUI while preserving composed V1 write aliases such
    as approved-location projection until the Excel adapter is retired.
    """

    def __init__(self, repository: Any) -> None:
        self._repository = repository

    def list(self, *, include_cancelled: bool = True) -> Sequence[SegmentReadModel]:
        segment_repository = import_module("app.segment_repository")
        return tuple(
            SegmentReadModel.from_mapping(row)
            for row in segment_repository.segment_records(
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
