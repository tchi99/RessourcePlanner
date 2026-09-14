from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class V1WebParityContractTests(unittest.TestCase):
    def test_react_core_cutover_surfaces_are_real_pages(self) -> None:
        app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")

        for component in (
            "PlanningPage",
            "MediumTermPage",
            "DemandsWorkspace",
            "ProjectsPage",
        ):
            with self.subTest(component=component):
                self.assertIn(f"<{component}", app)

        self.assertIn('view === "projects"', app)
        self.assertIn('view === "demands"', app)
        self.assertIn('view === "medium-term"', app)
        self.assertIn('view === "planning"', app)

    def test_segment_backend_surface_already_covers_v1_mutations(self) -> None:
        commands = (ROOT / "app/server/routes_commands.py").read_text(encoding="utf-8")
        reads = (ROOT / "app/server/routes_reads.py").read_text(encoding="utf-8")

        for route in (
            '@router.post("/segments"',
            '@router.patch("/segments/{segment_id}"',
            '@router.post("/segments/{segment_id}/cancel"',
            '@router.post("/segments/{segment_id}/assign"',
        ):
            with self.subTest(route=route):
                self.assertIn(route, commands)

        self.assertIn('@router.get("/segments")', reads)
        self.assertIn('@router.get("/segments/{segment_id}")', reads)

    def test_resource_sql_model_exists_but_admin_is_tracked_as_cutover_blocker(self) -> None:
        models = (ROOT / "app/infrastructure/sql/models.py").read_text(encoding="utf-8")
        reads = (ROOT / "app/server/routes_reads.py").read_text(encoding="utf-8")
        parity = (ROOT / "docs/V1_WEB_PARITY.md").read_text(encoding="utf-8")

        self.assertIn("class Resource(", models)
        self.assertIn("class ResourceAvailabilityRule(", models)
        self.assertIn('@router.get("/resources")', reads)
        self.assertIn("Bloqueur 1 — Administration Ressources & Disponibilités", parity)
        self.assertIn("#211", parity)

    def test_excel_specific_screens_are_explicitly_not_cutover_requirements(self) -> None:
        parity = (ROOT / "docs/V1_WEB_PARITY.md").read_text(encoding="utf-8")

        self.assertIn("Données Excel", parity)
        self.assertIn("SUPPRIMER AU CUTOVER", parity)
        self.assertIn("Paramètres Excel", parity)
        self.assertIn("Outlook / Thunderbird", parity)
        self.assertIn("REPORTER / REMPLACER", parity)


if __name__ == "__main__":
    unittest.main()
