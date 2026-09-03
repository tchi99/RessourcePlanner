from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from ..domain.demand_periods import DemandPeriodDefinition
from ..domain.planning_snapshot import PlanningSnapshot
from .read_models import DemandPeriodReadModel, DemandReadModel, SegmentReadModel


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


class DemandPeriodRepositoryPort(Protocol):
    """Persistence contract for requested periods and exclusive option selection."""

    def list_for_demand(
        self,
        demand_number: str,
        *,
        include_inactive: bool = False,
    ) -> Sequence[DemandPeriodReadModel]: ...

    def replace_for_demand(
        self,
        demand_number: str,
        periods: Sequence[DemandPeriodDefinition],
    ) -> Sequence[DemandPeriodReadModel]: ...

    def select_alternative(
        self,
        demand_number: str,
        alternative_group: str,
        period_id: str,
    ) -> None: ...

    def selections_for_demand(self, demand_number: str) -> Mapping[str, str]: ...


class SegmentRepositoryPort(Protocol):
    """Persistence contract required by operational segment workflows."""

    def list(self, *, include_cancelled: bool = True) -> Sequence[SegmentReadModel]: ...

    def get(self, segment_id: str) -> SegmentReadModel | None: ...

    def create(self, values: Mapping[str, Any]) -> str: ...

    def update(self, segment_id: str, updates: Mapping[str, Any]) -> None: ...


class PlanningReadRepositoryPort(Protocol):
    """Atomic read contract for one pure-planning calculation cycle.

    Implementations may read Excel, SQL Server or another store, but callers receive
    one immutable ``PlanningSnapshot`` and never coordinate physical tables/sheets.
    """

    def capture(self) -> PlanningSnapshot: ...
