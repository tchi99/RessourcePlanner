from __future__ import annotations

import sys
from multiprocessing import freeze_support

from nicegui import native, ui

from app.runtime_composition import install_planning_engine, install_runtime_features

# V1 still contains historical compatibility installers. They are now composed from
# one explicit application root instead of being scattered through this entry point.
# The composition root activates the NiceGUI compatibility shim before importing the
# historical feature modules and preserves the validated V1.8 installer order.
install_runtime_features()

from app.config import load_config
from app.excel_repository import ExcelRepository
from app.ui import PlannerUI


def main() -> None:
    config = load_config()
    # Planning-engine selection intentionally remains the final runtime composition
    # step so the authoritative pure dispatcher cannot be overwritten by a legacy
    # compatibility installer.
    install_planning_engine(config.planning_engine_mode)
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
    # Required by NiceGUI/PyInstaller native mode so spawned native-window processes
    # do not restart the complete application recursively.
    freeze_support()
    main()
