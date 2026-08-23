from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


class SegmentEditorUIArchitectureTests(unittest.TestCase):
    def test_explicit_editor_owns_authoritative_dialog_and_uses_service(self) -> None:
        source = (APP / "segment_editor_ui.py").read_text(encoding="utf-8")

        self.assertIn("def open_segment_editor(", source)
        self.assertIn("segment_service(owner.repo).create", source) if False else None
        self.assertIn("service = segment_service(owner.repo)", source)
        self.assertIn("service.create(data)", source)
        self.assertIn("service.update(", source)
        self.assertIn("service.cancel(", source)
        self.assertNotIn("from . import v13", source)
        self.assertNotIn("v13.", source)
        self.assertNotIn("v15_refinements", source)
        self.assertNotIn("rebuild_allocations_refined", source)

    def test_v15_refinements_no_longer_defines_segment_dialog(self) -> None:
        source = (APP / "v15_refinements.py").read_text(encoding="utf-8")

        self.assertNotIn("def _segment_dialog(", source)
        self.assertIn("from .segment_editor_ui import open_segment_editor", source)
        self.assertIn("v13._open_segment_dialog = open_segment_editor", source)
        self.assertIn("v14._open_segment_dialog_v14 = open_segment_editor", source)

    def test_segments_page_calls_explicit_editor_without_compat_module(self) -> None:
        source = (APP / "segments_page.py").read_text(encoding="utf-8")

        self.assertIn("from .segment_editor_ui import open_segment_editor", source)
        self.assertNotIn("segment_editor_compat", source)
        self.assertFalse((APP / "segment_editor_compat.py").exists())

    def test_v13_reexports_table_name_for_remaining_excel_compatibility(self) -> None:
        source = (APP / "v13.py").read_text(encoding="utf-8")
        self.assertIn("SEGMENT_TABLE,", source)


if __name__ == "__main__":
    unittest.main()
