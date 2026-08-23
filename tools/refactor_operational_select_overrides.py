from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
TESTS = ROOT / "tests"


def update_renderer(filename: str, module_name: str, render_call: str) -> None:
    path = APP / filename
    source = path.read_text(encoding="utf-8")

    import_anchor = "from .excel_repository import"
    if "from .ui_context import ensure_scoped_ui\n" not in source:
        index = source.find(import_anchor)
        if index < 0:
            raise RuntimeError(f"{filename}: import anchor not found")
        line_end = source.find("\n", index)
        # Some imports are multiline. Insert after the completed import statement.
        if source[index:line_end].rstrip().endswith("("):
            closing = source.find("\n)", line_end)
            if closing < 0:
                raise RuntimeError(f"{filename}: multiline import closing not found")
            line_end = closing + 2
        source = source[: line_end + 1] + "from .ui_context import ensure_scoped_ui\n" + source[line_end + 1 :]

    old_original = f"    original_select = {module_name}.ui.select\n"
    new_original = (
        f"    scoped_ui = ensure_scoped_ui(\n"
        f"        {module_name},\n"
        f"        scope_name=\"{module_name}_planning\",\n"
        f"        scoped_factories=(\"select\",),\n"
        f"    )\n"
        f"    original_select = scoped_ui.base_factory(\"select\")\n"
    )
    if old_original not in source and new_original not in source:
        raise RuntimeError(f"{filename}: original select marker not found")
    source = source.replace(old_original, new_original, 1)

    old_block = (
        f"    {module_name}.ui.select = select_proxy\n"
        f"    try:\n"
        f"        {render_call}\n"
        f"    finally:\n"
        f"        {module_name}.ui.select = original_select\n"
    )
    new_block = (
        "    with scoped_ui.override_factory(\"select\", select_proxy):\n"
        f"        {render_call}\n"
    )
    if old_block not in source and new_block not in source:
        raise RuntimeError(f"{filename}: assignment block not found")
    source = source.replace(old_block, new_block, 1)

    path.write_text(source, encoding="utf-8")


def update_tests() -> None:
    path = TESTS / "test_nicegui_global_mutations.py"
    source = path.read_text(encoding="utf-8")
    old = '''    def test_legacy_select_assignments_are_limited_and_scoped_before_render(self) -> None:\n        # The two historical renderers still use save/assign/restore syntax. They no\n        # longer point at process-wide nicegui.ui: operational_planning_compat installs\n        # a ContextVar-backed facade for both modules before any page is rendered.\n        offenders = sorted(\n            set(self._offenders("ui.select =") + self._offenders("nicegui_ui.select ="))\n        )\n        self.assertEqual(offenders, ["v16_refinements.py", "v17_refinements.py"])\n\n        setup = self._source("operational_planning_compat.py")\n        self.assertIn("ensure_scoped_ui(\\n        v16,", setup)\n        self.assertIn("ensure_scoped_ui(\\n        v17,", setup)\n        self.assertIn('scoped_factories=("select",)', setup)\n\n'''
    new = '''    def test_operational_select_overrides_use_context_managers(self) -> None:\n        offenders = sorted(\n            set(self._offenders("ui.select =") + self._offenders("nicegui_ui.select ="))\n        )\n        self.assertEqual(offenders, [])\n\n        for filename in ("v16_refinements.py", "v17_refinements.py"):\n            renderer = self._source(filename)\n            self.assertIn("ensure_scoped_ui(", renderer)\n            self.assertIn('with scoped_ui.override_factory("select", select_proxy):', renderer)\n            self.assertNotIn(".ui.select = select_proxy", renderer)\n\n'''
    if old not in source:
        raise RuntimeError("NiceGUI legacy select test block not found")
    source = source.replace(old, new, 1)
    path.write_text(source, encoding="utf-8")


def main() -> None:
    update_renderer("v16_refinements.py", "v16", "v16._render_planning_v16(self)")
    update_renderer("v17_refinements.py", "v17", "v17._render_planning(self)")
    update_tests()


if __name__ == "__main__":
    main()
