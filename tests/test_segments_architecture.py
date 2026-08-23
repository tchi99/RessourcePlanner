from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


class SegmentsArchitectureTests(unittest.TestCase):
    def test_segment_repository_is_ui_free_and_owns_excel_read_model(self) -> None:
        source = (APP / "segment_repository.py").read_text(encoding="utf-8")

        self.assertNotIn("nicegui", source)
        self.assertIn("def segment_records(", source)
        self.assertIn("def add_segment(", source)
        self.assertIn("def update_segment(", source)
        self.assertIn("def number(", source)
        self.assertIn('SEGMENT_SHEET = "SegmentsMO"', source)

    def test_v13_reexports_segment_repository_but_no_longer_owns_it(self) -> None:
        source = (APP / "v13.py").read_text(encoding="utf-8")

        self.assertIn("from .segment_repository import (", source)
        for definition in (
            "def segment_records(",
            "def add_segment(",
            "def update_segment(",
            "def _render_segments(",
            "def _clear_segment_filter(",
            "def _go_to_segments(",
        ):
            self.assertNotIn(definition, source)
        self.assertNotIn("PlannerUI.render_segments =", source)

    def test_explicit_segments_page_owns_render_and_filter_navigation(self) -> None:
        source = (APP / "segments_page.py").read_text(encoding="utf-8")

        self.assertIn("class SegmentsPage:", source)
        self.assertIn("def render(self)", source)
        self.assertIn("def clear_filter(self)", source)
        self.assertIn("def open_for_demand(self, demand", source)
        self.assertIn("from .segment_repository import number, segment_records", source)
        self.assertNotIn("from . import v13", source)

    def test_base_ui_routes_segments_without_versioned_renderer(self) -> None:
        source = (APP / "ui.py").read_text(encoding="utf-8")

        self.assertIn("from .segments_page import SegmentsPage", source)
        self.assertIn("self.segments_page = SegmentsPage(self)", source)
        self.assertIn('elif self.current_page == "segments":', source)
        self.assertIn("self.segments_page.render()", source)

    def test_request_page_uses_stable_segment_read_model_and_page_navigation(self) -> None:
        source = (APP / "demand_requests_page.py").read_text(encoding="utf-8")

        self.assertIn("from .segment_repository import number, segment_records", source)
        self.assertNotIn("from .v13 import segment_records", source)
        self.assertIn("self.owner.segments_page.open_for_demand(demand)", source)


if __name__ == "__main__":
    unittest.main()
