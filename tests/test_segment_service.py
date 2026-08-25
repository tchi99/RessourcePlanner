from __future__ import annotations

from pathlib import Path
import unittest

from app.application.segment_service import SegmentService


class SegmentServiceTests(unittest.TestCase):
    def test_create_persists_then_rebuilds_once(self) -> None:
        events: list[object] = []

        def create(repo, values):
            events.append(("create", repo, dict(values)))
            return "SEG-2026-0001"

        def update(repo, identifier, values):
            events.append(("update", repo, identifier, dict(values)))

        def rebuild(repo):
            events.append(("rebuild", repo))
            return {"allocated_hours": 8.0, "unallocated_hours": 0.0}

        service = SegmentService(
            "repo",
            create_record=create,
            update_record=update,
            rebuild_planning=rebuild,
        )
        identifier, summary = service.create(
            {"NoDemande": "DMO-1", "HeuresPrevues": 8}
        )

        self.assertEqual(identifier, "SEG-2026-0001")
        self.assertEqual(summary["allocated_hours"], 8.0)
        self.assertEqual([event[0] for event in events], ["create", "rebuild"])

    def test_update_and_cancel_rebuild_after_mutation(self) -> None:
        events: list[object] = []

        def create(repo, values):
            return "SEG-1"

        def update(repo, identifier, values):
            events.append((identifier, dict(values)))

        def rebuild(repo):
            events.append("rebuild")
            return {"unallocated_hours": 2.0}

        service = SegmentService(
            object(),
            create_record=create,
            update_record=update,
            rebuild_planning=rebuild,
        )
        service.update("SEG-1", {"HeuresPrevues": 6})
        service.cancel("SEG-1")

        self.assertEqual(events[0], ("SEG-1", {"HeuresPrevues": 6}))
        self.assertEqual(events[1], "rebuild")
        self.assertEqual(events[2], ("SEG-1", {"Statut": "Annulé"}))
        self.assertEqual(events[3], "rebuild")

    def test_empty_identifiers_are_rejected(self) -> None:
        service = SegmentService(
            object(),
            create_record=lambda repo, values: "SEG-1",
            update_record=lambda repo, identifier, values: None,
            rebuild_planning=lambda repo: {},
        )
        with self.assertRaises(ValueError):
            service.create({"NoDemande": ""})
        with self.assertRaises(ValueError):
            service.update("", {})

    def test_application_service_has_no_ui_storage_or_versioned_import(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "application"
            / "segment_service.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("nicegui", source)
        self.assertNotIn("excel_repository", source)
        self.assertNotIn("xlwings", source)
        self.assertNotIn("app.v13", source)
        self.assertNotIn("v15", source)
        self.assertIn("SegmentRepositoryPort", source)
        self.assertIn("from_repository_port", source)

    def test_excel_adapter_resolves_composed_segment_alias_lazily(self) -> None:
        root = Path(__file__).resolve().parents[1]
        runtime_source = (root / "app" / "application" / "runtime_services.py").read_text(
            encoding="utf-8"
        )
        adapter_source = (
            root / "app" / "infrastructure" / "excel" / "segment_repository.py"
        ).read_text(encoding="utf-8")

        self.assertIn("ExcelSegmentRepository(repository)", runtime_source)
        self.assertIn("SegmentService.from_repository_port(", runtime_source)
        self.assertIn('import_module("app.v13")', adapter_source)
        self.assertIn("v13.add_segment", adapter_source)
        self.assertIn("v13.update_segment", adapter_source)
        self.assertIn("rebuild_planning=_runtime_rebuild", runtime_source)


if __name__ == "__main__":
    unittest.main()
