from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PlanningRebuildCommand:
    """Explicit marker command for a full authoritative planning rebuild."""
