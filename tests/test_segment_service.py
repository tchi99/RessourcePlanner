from __future__ import annotations

from pathlib import Path
import unittest

from app.application.segment_service import SegmentService


class _Segments:
    def __init__(self) -> None:
        self.events: list[object] = []

    def list(self, *, include_cancelled=True):
        return ()

    def get(self, segment_id):
        return None

    def create(self, values):
        self.events.append(("create", dict(values)))
        return "SEG-2026-0001"

    def update(self, identifier, values):
        self.events.append(("update", identifier, dict(values)))


class _Planning:
    def __init__(self, events: list[object]) -> None:
        self.events = events

    def rebuild(self):
        self.events.append(("rebuild",))
        return {"allocated_hours": 8.0, "unallocated_hours": 0.0}


class SegmentServiceTests(unittest.TestCase):
    def test_create_persists_then_rebuilds_once(self) -> None:
        segments = _Segments()
        planning = _Planning(segments.events)
        service = SegmentService(segments, planning)

        identifier, summary = service.create(
            {"NoDemande": "DMO-1", "HeuresPrevues": 8}
        )

        self.assertEqual(identifier, "SEG-2026-0001")
        self.assertEqual(summary["allocated_hours"], 8.0)
        self.assertEqual(
            segments.events,
            [
                ("create", {"NoDemande": "DMO-1", "HeuresPrevues": 8}),
                ("rebuild",),
            ],
        )

    def test_update_and_cancel_rebuild_after_mutation(self) -> None:
        segments = _Segments()
        planning = _Planning(segments.events)
        service = SegmentService(segments, planning)

        service.update("SEG-1", {"HeuresPrevues": 6})
        service.cancel("SEG-1")

        self.assertEqual(
            segments.events,
            [
                ("update", "SEG-1", {"HeuresPrevues": 6}),
                ("rebuild",),
                ("update", "SEG-1", {"Statut": "Annulé"}),
                ("rebuild",),
            ],
        )

    def test_empty_identifiers_are_rejected(self) -> None:
        segments = _Segments()
        service = SegmentService(segments, _Planning(segments.events))
        with self.assertRaises(ValueError):
            service.create({"NoDemande": ""})
        with self.assertRaises(ValueError):
            service.update("", {})
        self.assertEqual(segments.events, [])

    def test_application_service_has_only_port_dependencies(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "application"
            / "segment_service.py"
        ).read_text(encoding="utf-8")

        for token in ("nicegui", "excel_repository", "xlwings", "app.v13", "v15"):
            self.assertNotIn(token, source)
        self.assertIn("SegmentRepositoryPort", source)
        self.assertIn("PlanningCommandPort", source)
        self.assertNotIn("repository_context", source)
        self.assertNotIn("rebuild_planning", source)

    def test_runtime_composition_uses_excel_ports_not_callbacks(self) -> None:
        root = Path(__file__).resolve().parents[1]
        runtime_source = (root / "app" / "application" / "runtime_services.py").read_text(
            encoding="utf-8"
        )
        adapter_source = (
            root / "app" / "infrastructure" / "excel" / "segment_repository.py"
        ).read_text(encoding="utf-8")

        self.assertIn("ExcelSegmentRepository(repository)", runtime_source)
        self.assertIn("ExcelPlanningCommandAdapter(repository)", runtime_source)
        self.assertIn("return SegmentService(", runtime_source)
        self.assertNotIn("rebuild_planning=lambda", runtime_source)
        self.assertIn('import_module("app.v13")', adapter_source)


if __name__ == "__main__":
    unittest.main()
