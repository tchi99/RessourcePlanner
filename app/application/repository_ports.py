from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from .read_models import DemandReadModel, SegmentReadModel


class DemandRepositoryPort(Protocol):
    """Persistence contract required by demand workflows.

    The contract deliberately exposes business-oriented records and generic commands;
    it does not mention Excel, SQLAlchemy or any physical schema.
    """

    def list(self) -> Sequence[DemandReadModel]: ...

    def get(self, number: str) -> DemandReadModel | None: ...

    def create(self, values: Mapping[str, Any], *, submit: bool = False) -> str: ...

    def update(
        self,
        number: str,
        updates: Mapping[str, Any],
        *,
        action: str,
        comment: str = "",
    ) -> None: ...


class SegmentRepositoryPort(Protocol):
    """Persistence contract required by operational segment workflows."""

    def list(self, *, include_cancelled: bool = True) -> Sequence[SegmentReadModel]: ...

    def get(self, segment_id: str) -> SegmentReadModel | None: ...

    def create(self, values: Mapping[str, Any]) -> str: ...

    def update(self, segment_id: str, updates: Mapping[str, Any]) -> None: ...
