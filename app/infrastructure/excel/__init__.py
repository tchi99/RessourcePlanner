"""Excel-backed implementations of application repository ports."""

from .demand_repository import ExcelDemandRepository
from .segment_repository import ExcelSegmentRepository

__all__ = ["ExcelDemandRepository", "ExcelSegmentRepository"]
