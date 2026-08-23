from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
TESTS = ROOT / "tests"


def _remove_ranges(source: str, ranges: list[tuple[int, int]]) -> str:
    lines = source.splitlines(keepends=True)
    for start, end in sorted(ranges, reverse=True):
        del lines[start - 1 : end]
    return "".join(lines)


def remove_class_methods(source: str, class_name: str, names: set[str]) -> str:
    tree = ast.parse(source)
    ranges: list[tuple[int, int]] = []
    found: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name in names:
                starts = [child.lineno, *(item.lineno for item in child.decorator_list)]
                ranges.append((min(starts), child.end_lineno or child.lineno))
                found.add(child.name)
    missing = names - found
    if missing:
        raise RuntimeError(f"Missing {class_name} methods: {sorted(missing)}")
    return _remove_ranges(source, ranges)


def remove_top_level_function(source: str, name: str) -> str:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            starts = [node.lineno, *(item.lineno for item in node.decorator_list)]
            return _remove_ranges(source, [(min(starts), node.end_lineno or node.lineno)])
    raise RuntimeError(f"Top-level function {name} not found")


def remove_nested_function(source: str, parent: str, name: str) -> str:
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name != parent:
            continue
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == name:
                starts = [child.lineno, *(item.lineno for item in child.decorator_list)]
                return _remove_ranges(source, [(min(starts), child.end_lineno or child.lineno)])
    raise RuntimeError(f"Nested function {parent}.{name} not found")


def edit_ui() -> None:
    path = APP / "ui.py"
    source = path.read_text(encoding="utf-8")
    import_anchor = "from .config import save_workbook_path\n"
    if "from .demand_requests_page import DemandRequestsPage\n" not in source:
        source = source.replace(
            import_anchor,
            import_anchor + "from .demand_requests_page import DemandRequestsPage\n",
            1,
        )

    old_refresh = '''        # Refreshables créés à partir de méthodes liées :\n        # plus robuste qu'un décorateur directement sur la classe.\n        self.render_content = ui.refreshable(\n            self._render_content\n        )\n        self.request_actions = ui.refreshable(\n            self._request_actions\n        )\n'''
    new_refresh = '''        # La page Demandes possède désormais son propre rendu et ses actions.\n        self.demand_requests_page = DemandRequestsPage(self)\n\n        # Refreshable principal conservé sur le shell historique pendant l'extraction\n        # progressive des autres pages. L'alias request_actions protège les adaptateurs\n        # encore susceptibles de rafraîchir la sélection sans réintroduire de méthode UI.\n        self.render_content = ui.refreshable(\n            self._render_content\n        )\n        self.request_actions = self.demand_requests_page.request_actions\n'''
    if old_refresh not in source:
        raise RuntimeError("PlannerUI refreshable block changed")
    source = source.replace(old_refresh, new_refresh, 1)

    old_render = '''        elif self.current_page == "requests":\n            self.render_requests()\n'''
    new_render = '''        elif self.current_page == "requests":\n            self.demand_requests_page.render()\n'''
    if old_render not in source:
        raise RuntimeError("PlannerUI requests render branch changed")
    source = source.replace(old_render, new_render, 1)

    source = remove_class_methods(
        source,
        "PlannerUI",
        {"render_requests", "_request_actions", "open_planning_dialog", "_demand_grid_row"},
    )
    path.write_text(source, encoding="utf-8")


def edit_features() -> None:
    path = APP / "features.py"
    source = path.read_text(encoding="utf-8")
    source = remove_nested_function(source, "install_features", "request_actions")
    for line in (
        "    original_request_actions = ui_module.PlannerUI._request_actions\n",
        "    ui_module.PlannerUI._request_actions = request_actions\n",
    ):
        if line not in source:
            raise RuntimeError(f"features.py expected line missing: {line.strip()}")
        source = source.replace(line, "", 1)
    path.write_text(source, encoding="utf-8")


def edit_bugfixes() -> None:
    path = APP / "bugfixes.py"
    source = path.read_text(encoding="utf-8")
    source = remove_nested_function(source, "install_bugfixes", "open_planning_dialog")
    for line in (
        "    original_planning_dialog = ui_module.PlannerUI.open_planning_dialog\n",
        "    ui_module.PlannerUI.open_planning_dialog = open_planning_dialog\n",
    ):
        if line not in source:
            raise RuntimeError(f"bugfixes.py expected line missing: {line.strip()}")
        source = source.replace(line, "", 1)
    path.write_text(source, encoding="utf-8")


def edit_v13() -> None:
    path = APP / "v13.py"
    source = path.read_text(encoding="utf-8")
    source = remove_top_level_function(source, "_request_actions_v13")
    assignment = "    ui_module.PlannerUI._request_actions = _request_actions_v13\n"
    if assignment not in source:
        raise RuntimeError("v13 request action assignment missing")
    source = source.replace(assignment, "", 1)
    path.write_text(source, encoding="utf-8")


def edit_runtime_composition() -> None:
    path = APP / "runtime_composition.py"
    source = path.read_text(encoding="utf-8")
    for line in (
        '    CompositionStep("demand_service_ui", "application"),\n',
        "    from .demand_service_ui import install_demand_service_ui\n",
        '        ("demand_service_ui", install_demand_service_ui),\n',
    ):
        if line not in source:
            raise RuntimeError(f"runtime composition expected line missing: {line.strip()}")
        source = source.replace(line, "", 1)
    path.write_text(source, encoding="utf-8")


def edit_demand_service_tests() -> None:
    path = TESTS / "test_demand_service.py"
    source = path.read_text(encoding="utf-8")
    old_legacy_tail = '''        self.assertFalse((root / "app" / "demand_legacy_cleanup.py").exists())\n        service_ui = (root / "app" / "demand_service_ui.py").read_text(encoding="utf-8")\n        self.assertNotIn("approve_demand", service_ui)\n'''
    new_legacy_tail = '''        self.assertFalse((root / "app" / "demand_legacy_cleanup.py").exists())\n        self.assertFalse((root / "app" / "demand_service_ui.py").exists())\n'''
    if old_legacy_tail not in source:
        raise RuntimeError("DemandService legacy test block changed")
    source = source.replace(old_legacy_tail, new_legacy_tail, 1)

    start = source.index("    def test_base_ui_no_longer_defines_dormant_demand_lifecycle")
    end = source.index("\n\n\nif __name__ == \"__main__\":", start)
    replacement = '''    def test_explicit_request_page_owns_demand_lifecycle(self) -> None:\n        root = Path(__file__).resolve().parents[1]\n        ui_source = (root / "app" / "ui.py").read_text(encoding="utf-8")\n        page_source = (root / "app" / "demand_requests_page.py").read_text(\n            encoding="utf-8"\n        )\n        v13_source = (root / "app" / "v13.py").read_text(encoding="utf-8")\n        features_source = (root / "app" / "features.py").read_text(encoding="utf-8")\n\n        self.assertFalse((root / "app" / "demand_service_ui.py").exists())\n        self.assertIn("DemandRequestsPage", ui_source)\n        self.assertIn("self.demand_requests_page.render()", ui_source)\n        for definition in (\n            "def render_requests(",\n            "def _request_actions(",\n            "def open_planning_dialog(",\n            "def _demand_grid_row(",\n        ):\n            self.assertNotIn(definition, ui_source)\n\n        for service_call in (\n            "demand_service(self.owner.repo).submit(",\n            "demand_service(self.owner.repo).approve(",\n            "demand_service(self.owner.repo).request_correction(",\n            "demand_service(self.owner.repo).cancel(",\n        ):\n            self.assertIn(service_call, page_source)\n        self.assertIn("open_edit_request_dialog", page_source)\n        self.assertIn("Gérer les segments", page_source)\n        self.assertNotIn("_request_actions_v13", v13_source)\n        self.assertNotIn("PlannerUI._request_actions", features_source)\n'''
    source = source[:start] + replacement + source[end:]
    path.write_text(source, encoding="utf-8")


def edit_runtime_tests() -> None:
    path = TESTS / "test_runtime_composition.py"
    source = path.read_text(encoding="utf-8")
    source = source.replace(
        '        self.assertLess(names.index("planning_service_ui"), names.index("demand_service_ui"))\n'
        '        self.assertLess(names.index("demand_service_ui"), names.index("allocation_service_ui"))\n',
        '        self.assertLess(names.index("planning_service_ui"), names.index("allocation_service_ui"))\n',
        1,
    )
    source = source.replace(
        '                "planning_service_ui",\n                "demand_service_ui",\n                "allocation_service_ui",\n',
        '                "planning_service_ui",\n                "allocation_service_ui",\n',
        1,
    )
    source = source.replace(
        '            "demand_legacy_cleanup.py",\n',
        '            "demand_legacy_cleanup.py",\n            "demand_service_ui.py",\n',
        1,
    )
    path.write_text(source, encoding="utf-8")


def main() -> None:
    edit_ui()
    edit_features()
    edit_bugfixes()
    edit_v13()
    edit_runtime_composition()
    edit_demand_service_tests()
    edit_runtime_tests()

    service_ui = APP / "demand_service_ui.py"
    if not service_ui.exists():
        raise RuntimeError("demand_service_ui.py already missing")
    service_ui.unlink()


if __name__ == "__main__":
    main()
