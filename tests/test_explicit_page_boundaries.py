from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


class ExplicitPageBoundaryTests(unittest.TestCase):
    def test_explicit_pages_do_not_import_versioned_modules(self) -> None:
        for filename in (
            "operational_planning_page.py",
            "medium_term_page.py",
            "demand_requests_page.py",
            "segments_page.py",
        ):
            source = (APP / filename).read_text(encoding="utf-8")
            tree = ast.parse(source)
            imported_modules: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported_modules.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    imported_modules.append(module)
            offenders = [
                module
                for module in imported_modules
                if module.split(".")[-1].startswith(("v13", "v14", "v15", "v16", "v17", "v18"))
            ]
            self.assertEqual(offenders, [], f"{filename}: {offenders}")

    def test_segments_page_does_not_eagerly_import_segment_editor(self) -> None:
        path = APP / "segments_page.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))

        top_level_modules = {
            node.module or ""
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
        }
        self.assertNotIn(
            "segment_editor_ui",
            top_level_modules,
            "SegmentsPage is imported while PlannerUI starts; the editor must stay lazy to avoid bugfixes -> ui -> segments_page -> segment_editor_ui -> bugfixes.",
        )

        helper = next(
            (
                node
                for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "_open_segment_editor"
            ),
            None,
        )
        self.assertIsNotNone(helper)
        lazy_modules = {
            node.module or ""
            for node in ast.walk(helper)
            if isinstance(node, ast.ImportFrom)
        }
        self.assertIn("segment_editor_ui", lazy_modules)

    def test_medium_term_page_owns_route_and_read_signature(self) -> None:
        source = (APP / "medium_term_page.py").read_text(encoding="utf-8")

        self.assertIn('if self.current_page == "medium_term":', source)
        self.assertIn("page.render()", source)
        for sheet in (
            "Liste_Effort",
            "DemandesMO",
            "SegmentsMO",
            "AllocationsMO",
            "Disponibilites",
            "RessourcesMO",
        ):
            self.assertIn(f'"{sheet}"', source)

    def test_v18_installers_are_not_runtime_authorities(self) -> None:
        source = (APP / "runtime_composition.py").read_text(encoding="utf-8")

        self.assertNotIn('CompositionStep("v18_features"', source)
        self.assertNotIn('CompositionStep("v18_refinements"', source)
        self.assertIn('CompositionStep("effort_identity", "compatibility")', source)
        self.assertIn('CompositionStep("demand_cancellation", "compatibility")', source)
        self.assertIn('CompositionStep("medium_term_renderer", "compatibility")', source)
        self.assertIn('CompositionStep("medium_term_page", "application")', source)


if __name__ == "__main__":
    unittest.main()
