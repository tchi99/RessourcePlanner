from __future__ import annotations

from pathlib import Path
import unittest

from app.operational_planning_work_sections import (
    WorkSectionsBindings,
    visible_pending_demands,
    visible_unassigned_segments,
)


def _bindings() -> WorkSectionsBindings:
    return WorkSectionsBindings(
        all_projects="Tous les projets",
        all_confirmations="Tous",
        demand_confirmation=lambda demand: str(demand.get("Confirmation") or "Confirmée"),
        segment_competence=lambda segment, demands: None,
        required_class=lambda repo, segment: None,
        number=lambda value: float(value or 0),
        make_draggable=lambda element, payload: element,
        open_recommendation_dialog=lambda owner, segment: None,
        open_segment_dialog=lambda owner, segment: None,
        open_request_dialog=lambda owner, demand: None,
        date_text=lambda owner, value: str(value or ""),
    )


class OperationalPlanningWorkSectionsTests(unittest.TestCase):
    def test_unassigned_filter_uses_project_and_demand_confirmation(self) -> None:
        unassigned = [
            {"IDSegment": "S1", "NumeroProjet": "100", "NoDemande": "D1"},
            {"IDSegment": "S2", "NumeroProjet": "100", "NoDemande": "D2"},
            {"IDSegment": "S3", "NumeroProjet": "200", "NoDemande": "D3"},
        ]
        demands = {
            "D1": {"Confirmation": "Confirmée"},
            "D2": {"Confirmation": "Tentative"},
            "D3": {"Confirmation": "Confirmée"},
        }

        rows = visible_unassigned_segments(
            unassigned,
            demands,
            "100",
            "Tentative",
            bindings=_bindings(),
        )

        self.assertEqual([row["IDSegment"] for row in rows], ["S2"])

    def test_pending_filter_preserves_all_values_and_specific_filters(self) -> None:
        pending = [
            {"NoDemande": "D1", "NumeroProjet": "100", "Confirmation": "Confirmée"},
            {"NoDemande": "D2", "NumeroProjet": "100", "Confirmation": "Tentative"},
            {"NoDemande": "D3", "NumeroProjet": "200", "Confirmation": "Confirmée"},
        ]

        all_rows = visible_pending_demands(
            pending,
            "Tous les projets",
            "Tous",
            bindings=_bindings(),
        )
        filtered = visible_pending_demands(
            pending,
            "100",
            "Confirmée",
            bindings=_bindings(),
        )

        self.assertEqual(len(all_rows), 3)
        self.assertEqual([row["NoDemande"] for row in filtered], ["D1"])

    def test_extracted_renderer_has_no_versioned_imports(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "operational_planning_work_sections.py"
        ).read_text(encoding="utf-8")

        for versioned in ("v13", "v14", "v15", "v16", "v17"):
            self.assertNotIn(f"from . import {versioned}", source)
            self.assertNotIn(f"from .{versioned}", source)

    def test_v17_delegates_work_sections_instead_of_rendering_them_inline(self) -> None:
        source = (
            Path(__file__).resolve().parents[1] / "app" / "v17.py"
        ).read_text(encoding="utf-8")

        self.assertIn("render_operational_planning_work_sections(", source)
        self.assertNotIn("visible_unassigned = [", source)
        self.assertNotIn("visible_pending = [", source)
        self.assertNotIn("v14_engine.segment_competence", source)
        self.assertNotIn("make_draggable(", source)


if __name__ == "__main__":
    unittest.main()
