"""Application-service layer for RessourcePlanner.

This package contains orchestration that can be called from NiceGUI today and from
FastAPI/Teams adapters later. Business rules remain in the domain/planning engine;
transport/UI concerns must not leak into this package.
"""

from .planning_service import PlanningService

__all__ = ["PlanningService"]
