from __future__ import annotations

from nicegui import ui

from app.bugfixes import install_bugfixes
from app.config import load_config
from app.excel_repository import ExcelRepository
from app.features import install_features
from app.features_runtime import apply_runtime_optimizations
from app.ui import PlannerUI
from app.v13 import install_v13_features
from app.v13_fixes import install_v13_fixes
from app.v14 import install_v14_features
from app.v14_fixes import install_v14_fixes
from app.v14_runtime import install_v14_runtime
from app.v15 import install_v15_features
from app.v15_refinements import install_v15_refinements
from app.v16 import install_v16_features
from app.v16_refinements import install_v16_refinements
from app.v17 import install_v17_features
from app.v17_refinements import install_v17_refinements
from app.v17_sort_fix import install_v17_sort_fix


apply_runtime_optimizations()
install_features()
install_bugfixes()
install_v13_features()
install_v13_fixes()
install_v14_features()
install_v14_fixes()
install_v14_runtime()
install_v15_features()
install_v15_refinements()
install_v16_features()
install_v16_refinements()
install_v17_features()
install_v17_refinements()
install_v17_sort_fix()


def main() -> None:
    config = load_config()
    repo = ExcelRepository(config.workbook, save_on_write=config.save_on_write)

    @ui.page("/")
    def index() -> None:
        PlannerUI(repo, refresh_seconds=config.refresh_seconds).build()

    ui.run(
        title="Planification MO — V1.7",
        host=config.host,
        port=config.port,
        reload=False,
        show=True,
        favicon="📅",
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
