from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


IMPORT_LINE = "from .operational_planning_page import register_operational_planning_renderer\n"


def replace_once(path: Path, old: str, new: str) -> None:
    source = path.read_text(encoding="utf-8")
    if old not in source:
        raise RuntimeError(f"Expected marker not found in {path.name}: {old!r}")
    source = source.replace(old, new, 1)
    path.write_text(source, encoding="utf-8")


def ensure_import(path: Path, anchor: str) -> None:
    source = path.read_text(encoding="utf-8")
    if IMPORT_LINE in source:
        return
    if anchor not in source:
        raise RuntimeError(f"Import anchor not found in {path.name}: {anchor!r}")
    source = source.replace(anchor, anchor + IMPORT_LINE, 1)
    path.write_text(source, encoding="utf-8")


def main() -> None:
    v15 = APP / "v15_refinements.py"
    ensure_import(v15, "from .services import week_days\n")
    replace_once(
        v15,
        "    ui_module.PlannerUI.render_planning = _render_planning\n",
        "    register_operational_planning_renderer(_render_planning)\n",
    )

    v16 = APP / "v16_refinements.py"
    ensure_import(v16, "from .ui_context import ensure_scoped_ui\n")
    replace_once(
        v16,
        "    ui_module.PlannerUI.render_planning = _render_planning\n",
        "    register_operational_planning_renderer(_render_planning)\n",
    )

    v17 = APP / "v17_refinements.py"
    ensure_import(v17, "from .ui_context import ensure_scoped_ui\n")
    replace_once(
        v17,
        "    ui_module.PlannerUI.render_planning = _render_planning\n",
        "    register_operational_planning_renderer(_render_planning)\n",
    )

    sort_fix = APP / "v17_sort_fix.py"
    ensure_import(sort_fix, "from .bugfixes import schedulable_technicians\n")
    replace_once(
        sort_fix,
        "    ui_module.PlannerUI.render_planning = render_planning\n",
        "    register_operational_planning_renderer(render_planning)\n",
    )


if __name__ == "__main__":
    main()
