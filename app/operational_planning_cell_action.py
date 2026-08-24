from __future__ import annotations

from datetime import date
from typing import Any, Callable


CellShiftOpener = Callable[[Any, str, date], None]

_registered_cell_shift_opener: CellShiftOpener | None = None


def register_operational_planning_cell_shift_opener(opener: CellShiftOpener) -> None:
    """Register the application action used by the '+' button in planning cells."""
    if not callable(opener):
        raise TypeError("L'action de cellule du planning doit être appelable.")
    global _registered_cell_shift_opener
    _registered_cell_shift_opener = opener


def open_operational_planning_cell_shift(owner: Any, technician: str, day: date) -> None:
    """Dispatch one planning-cell '+' action without depending on a V1.x module."""
    opener = _registered_cell_shift_opener
    if opener is None:
        raise RuntimeError("Aucune action de cellule du planning n'est enregistrée.")
    opener(owner, technician, day)
