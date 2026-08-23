from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
TESTS = ROOT / "tests"


def update_editor() -> None:
    path = APP / "segment_editor_ui.py"
    source = path.read_text(encoding="utf-8")
    old = '''        if selected_number:\n            demand_select.props("readonly")\n\n        with ui.row().classes("w-full"):\n'''
    new = '''        if selected_number:\n            demand_select.props("readonly")\n            if editing and current_demand:\n                demand_select.props("append-icon=open_in_new")\n                demand_select.on(\n                    "click:append",\n                    lambda _event: owner.open_edit_request_dialog(current_demand),\n                )\n                demand_select.tooltip("Ouvrir et modifier la demande associée")\n\n        with ui.row().classes("w-full"):\n'''
    if old not in source:
        raise RuntimeError("segment editor demand select block not found")
    source = source.replace(old, new, 1)
    path.write_text(source, encoding="utf-8")


def update_v15_alias() -> None:
    path = APP / "v15_refinements.py"
    source = path.read_text(encoding="utf-8")
    anchor = 'MISSING_ALLOCATION_TYPE = "Hors horaire requis"\n'
    alias = '''MISSING_ALLOCATION_TYPE = "Hors horaire requis"\n\n# Transitional symbol for historical v16/v17 renderers. The implementation is now\n# the explicit editor above and no longer belongs to this versioned module.\n_segment_dialog = open_segment_editor\n'''
    if "\n_segment_dialog = open_segment_editor\n" not in source:
        if anchor not in source:
            raise RuntimeError("v15 alias anchor not found")
        source = source.replace(anchor, alias, 1)
    path.write_text(source, encoding="utf-8")


def update_runtime_composition() -> None:
    path = APP / "runtime_composition.py"
    source = path.read_text(encoding="utf-8")
    source = source.replace(
        '    CompositionStep("segment_navigation_compat", "compatibility"),\n',
        "",
    )
    source = source.replace(
        "    from .segment_navigation_compat import install_segment_navigation_compat\n",
        "",
    )
    source = source.replace(
        '        ("segment_navigation_compat", install_segment_navigation_compat),\n',
        "",
    )
    path.write_text(source, encoding="utf-8")


def update_runtime_tests() -> None:
    path = TESTS / "test_runtime_composition.py"
    source = path.read_text(encoding="utf-8")
    source = source.replace(
        '        self.assertLess(names.index("resource_class_compat"), names.index("segment_navigation_compat"))\n'
        '        self.assertLess(names.index("segment_navigation_compat"), names.index("location_projection"))\n',
        '        self.assertLess(names.index("resource_class_compat"), names.index("location_projection"))\n',
    )
    source = source.replace('            "segment_navigation_compat",\n', "")
    source = source.replace(
        '            "demand_service_ui.py",\n',
        '            "demand_service_ui.py",\n            "segment_navigation_compat.py",\n            "segment_editor_compat.py",\n',
    )
    path.write_text(source, encoding="utf-8")


def update_nicegui_tests() -> None:
    path = TESTS / "test_nicegui_global_mutations.py"
    source = path.read_text(encoding="utf-8")
    old = '''    def test_segment_parent_navigation_reuses_scoped_facade(self) -> None:\n        source = self._source("segment_navigation_compat.py")\n        self.assertIn("ensure_scoped_ui(", source)\n        self.assertIn('with scoped_ui.override_factory("select", select_with_parent_link):', source)\n        self.assertNotIn("ContextVar", source)\n        self.assertNotIn("ui.select =", source)\n\n'''
    new = '''    def test_segment_parent_navigation_is_owned_by_explicit_editor(self) -> None:\n        source = self._source("segment_editor_ui.py")\n        self.assertIn('demand_select.props("append-icon=open_in_new")', source)\n        self.assertIn("owner.open_edit_request_dialog(current_demand)", source)\n        self.assertFalse(\n            (Path(__file__).resolve().parents[1] / "app" / "segment_navigation_compat.py").exists()\n        )\n\n'''
    if old not in source:
        raise RuntimeError("NiceGUI segment navigation test not found")
    source = source.replace(old, new, 1)
    path.write_text(source, encoding="utf-8")


def main() -> None:
    update_editor()
    update_v15_alias()
    update_runtime_composition()
    update_runtime_tests()
    update_nicegui_tests()


if __name__ == "__main__":
    main()
