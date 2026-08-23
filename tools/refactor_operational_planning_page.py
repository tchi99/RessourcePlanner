from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
TESTS = ROOT / "tests"


def update_ui() -> None:
    path = APP / "ui.py"
    source = path.read_text(encoding="utf-8")

    import_anchor = "from .demand_requests_page import DemandRequestsPage\n"
    page_import = "from .operational_planning_page import OperationalPlanningPage\n"
    if page_import not in source:
        if import_anchor not in source:
            raise RuntimeError("ui operational page import anchor not found")
        source = source.replace(import_anchor, import_anchor + page_import, 1)

    old_init = '''        self.demand_requests_page = DemandRequestsPage(self)\n        self.segments_page = SegmentsPage(self)\n\n'''
    new_init = '''        self.demand_requests_page = DemandRequestsPage(self)\n        self.segments_page = SegmentsPage(self)\n        planning_renderer = getattr(type(self), "_operational_planning_renderer", None)\n        if not callable(planning_renderer):\n            planning_renderer = type(self).render_planning\n        self.operational_planning_page = OperationalPlanningPage(\n            self, planning_renderer\n        )\n\n'''
    if old_init not in source:
        raise RuntimeError("ui page initialization block not found")
    source = source.replace(old_init, new_init, 1)

    old_route = '''        elif self.current_page == "planning":\n            self.render_planning()\n'''
    new_route = '''        elif self.current_page == "planning":\n            self.operational_planning_page.render()\n'''
    if old_route not in source:
        raise RuntimeError("ui planning route not found")
    source = source.replace(old_route, new_route, 1)
    path.write_text(source, encoding="utf-8")


def update_composition() -> None:
    path = APP / "runtime_composition.py"
    source = path.read_text(encoding="utf-8")

    manifest_anchor = '    CompositionStep("location_projection", "compatibility"),\n'
    manifest_line = '    CompositionStep("operational_planning_page", "application"),\n'
    if manifest_line not in source:
        if manifest_anchor not in source:
            raise RuntimeError("composition manifest anchor not found")
        source = source.replace(manifest_anchor, manifest_anchor + manifest_line, 1)

    import_anchor = "    from .operational_planning_compat import install_operational_planning_compat\n"
    import_line = "    from .operational_planning_page import install_operational_planning_page\n"
    if import_line not in source:
        if import_anchor not in source:
            raise RuntimeError("composition import anchor not found")
        source = source.replace(import_anchor, import_anchor + import_line, 1)

    installer_anchor = '        ("location_projection", install_location_projection),\n'
    installer_line = '        ("operational_planning_page", install_operational_planning_page),\n'
    if installer_line not in source:
        if installer_anchor not in source:
            raise RuntimeError("composition installer anchor not found")
        source = source.replace(installer_anchor, installer_anchor + installer_line, 1)

    path.write_text(source, encoding="utf-8")


def update_runtime_tests() -> None:
    path = TESTS / "test_runtime_composition.py"
    source = path.read_text(encoding="utf-8")

    old_order = '''        self.assertLess(names.index("resource_class_compat"), names.index("location_projection"))\n        self.assertLess(names.index("location_projection"), names.index("demand_editor_ui"))\n'''
    new_order = '''        self.assertLess(names.index("resource_class_compat"), names.index("location_projection"))\n        self.assertLess(names.index("location_projection"), names.index("operational_planning_page"))\n        self.assertLess(names.index("operational_planning_page"), names.index("demand_editor_ui"))\n'''
    if old_order not in source:
        raise RuntimeError("runtime composition ordering block not found")
    source = source.replace(old_order, new_order, 1)

    old_app = '''            [\n                "demand_editor_ui",\n                "planning_service_ui",\n                "allocation_service_ui",\n                "pure_validation_ui",\n            ],\n'''
    new_app = '''            [\n                "operational_planning_page",\n                "demand_editor_ui",\n                "planning_service_ui",\n                "allocation_service_ui",\n                "pure_validation_ui",\n            ],\n'''
    if old_app not in source:
        raise RuntimeError("runtime application list not found")
    source = source.replace(old_app, new_app, 1)
    path.write_text(source, encoding="utf-8")


def add_page_tests() -> None:
    path = TESTS / "test_operational_planning_page.py"
    if path.exists():
        raise RuntimeError("operational planning page test already exists")
    path.write_text(
        '''from __future__ import annotations\n\nfrom pathlib import Path\nimport unittest\n\nfrom app.operational_planning_page import OperationalPlanningPage\n\n\nROOT = Path(__file__).resolve().parents[1]\nAPP = ROOT / "app"\n\n\nclass OperationalPlanningPageTests(unittest.TestCase):\n    def test_page_invokes_injected_renderer_with_owner(self) -> None:\n        owner = object()\n        calls: list[object] = []\n        page = OperationalPlanningPage(owner, calls.append)\n\n        page.render()\n\n        self.assertEqual(calls, [owner])\n\n    def test_base_ui_routes_planning_through_explicit_page(self) -> None:\n        source = (APP / "ui.py").read_text(encoding="utf-8")\n        self.assertIn("from .operational_planning_page import OperationalPlanningPage", source)\n        self.assertIn("self.operational_planning_page = OperationalPlanningPage(", source)\n        self.assertIn("self.operational_planning_page.render()", source)\n        self.assertNotIn('elif self.current_page == "planning":\\n            self.render_planning()', source)\n\n    def test_installer_captures_final_renderer_without_importing_versioned_modules(self) -> None:\n        source = (APP / "operational_planning_page.py").read_text(encoding="utf-8")\n        self.assertIn('getattr(ui_module.PlannerUI, "render_planning", None)', source)\n        self.assertIn("PlannerUI._operational_planning_renderer = renderer", source)\n        for token in ("import v13", "import v15", "import v16", "import v17", "import v18"):\n            self.assertNotIn(token, source)\n\n\nif __name__ == "__main__":\n    unittest.main()\n''',
        encoding="utf-8",
    )


def main() -> None:
    update_ui()
    update_composition()
    update_runtime_tests()
    add_page_tests()


if __name__ == "__main__":
    main()
