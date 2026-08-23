from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


def remove_top_level_function(source: str, name: str) -> str:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    matches = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one {name}, got {len(matches)}")
    node = matches[0]
    del lines[node.lineno - 1 : node.end_lineno or node.lineno]
    return "".join(lines)


def update_v13() -> None:
    path = APP / "v13.py"
    source = path.read_text(encoding="utf-8")
    marker = "    SEGMENT_SHEET,\n"
    if "    SEGMENT_TABLE,\n" not in source:
        if marker not in source:
            raise RuntimeError("SEGMENT_SHEET import marker not found")
        source = source.replace(marker, marker + "    SEGMENT_TABLE,\n", 1)
    path.write_text(source, encoding="utf-8")


def update_segments_page() -> None:
    path = APP / "segments_page.py"
    source = path.read_text(encoding="utf-8")
    source = source.replace(
        "from .segment_editor_compat import open_segment_editor",
        "from .segment_editor_ui import open_segment_editor",
    )
    path.write_text(source, encoding="utf-8")


def update_v15_refinements() -> None:
    path = APP / "v15_refinements.py"
    source = path.read_text(encoding="utf-8")
    source = remove_top_level_function(source, "_segment_dialog")

    import_anchor = "from .services import week_days\n"
    editor_import = "from .segment_editor_ui import open_segment_editor\n"
    if editor_import not in source:
        if import_anchor not in source:
            raise RuntimeError("v15_refinements import anchor not found")
        source = source.replace(import_anchor, import_anchor + editor_import, 1)

    # Internal callbacks in this historical renderer now call the explicit editor.
    source = source.replace("_segment_dialog(", "open_segment_editor(")
    source = source.replace(
        "v14._open_segment_dialog_v14 = _segment_dialog",
        "v14._open_segment_dialog_v14 = open_segment_editor",
    )
    source = source.replace(
        "v13._open_segment_dialog = _segment_dialog",
        "v13._open_segment_dialog = open_segment_editor",
    )

    # Keep a narrow compatibility alias for v16/v17 until their renderer extraction.
    alias_anchor = "SEGMENT_OVERTIME_FIELD = \"HorsHoraireAutorise\"\n"
    alias = "\n# Transitional alias for historical renderers; implementation lives in segment_editor_ui.\n_segment_dialog = open_segment_editor\n"
    if "_segment_dialog = open_segment_editor" not in source:
        source = source.replace(alias_anchor, alias_anchor + alias, 1)

    path.write_text(source, encoding="utf-8")


def main() -> None:
    update_v13()
    update_segments_page()
    update_v15_refinements()


if __name__ == "__main__":
    main()
