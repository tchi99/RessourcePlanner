from __future__ import annotations

import sys
from multiprocessing import freeze_support

from nicegui import native, ui

from app.runtime_composition import install_planning_engine, install_runtime_features

# V1 still contains historical compatibility installers. They are composed from one
# explicit application root so their order remains visible while the architecture is
# progressively consolidated.
install_runtime_features()

from app.config import load_config
from app.excel_repository import ExcelRepository
from app.ui import PlannerUI


def main() -> None:
    config = load_config()
    # V1.8B is complete: the pure planning engine is the sole authoritative runtime.
    # It is installed last so no historical compatibility installer can overwrite it.
    install_planning_engine()
    repo = ExcelRepository(config.workbook, save_on_write=config.save_on_write)
    packaged = bool(getattr(sys, "frozen", False))

    @ui.page("/")
    def index() -> None:
        PlannerUI(repo, refresh_seconds=config.refresh_seconds).build()

    ui.run(
        title="Planification MO — V1.8",
        host="127.0.0.1" if packaged else config.host,
        port=native.find_open_port() if packaged else config.port,
        reload=False,
        show=not packaged,
        native=packaged,
        window_size=(1500, 950) if packaged else None,
        favicon="📅",
    )


if __name__ == "__main__":
    freeze_support()
    main()
