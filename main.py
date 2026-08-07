from __future__ import annotations

from nicegui import ui

from app.config import load_config
from app.excel_repository import ExcelRepository
from app.features import install_features
from app.features_runtime import apply_runtime_optimizations
from app.ui import PlannerUI


apply_runtime_optimizations()
install_features()


def main() -> None:
    config = load_config()
    repo = ExcelRepository(config.workbook, save_on_write=config.save_on_write)

    @ui.page("/")
    def index() -> None:
        PlannerUI(repo, refresh_seconds=config.refresh_seconds).build()

    ui.run(
        title="Planification MO — V1.2",
        host=config.host,
        port=config.port,
        reload=False,
        show=True,
        favicon="📅",
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
