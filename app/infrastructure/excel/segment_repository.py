from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ...application.read_models import SegmentReadModel
from ...application.repository_ports import SegmentRepositoryPort
from ...excel_repository import ExcelRepository
from ...segment_repository import add_segment, segment_records, update_segment


class ExcelSegmentRepository(SegmentRepositoryPort):
    """Excel implementation of the operational segment persistence contract."""

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
        return str(add_segment(self._repository, dict(values)))

    def update(self, segment_id: str, updates: Mapping[str, Any]) -> None:
        update_segment(self._repository, str(segment_id), dict(updates))
