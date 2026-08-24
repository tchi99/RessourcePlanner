from __future__ import annotations

import unittest

from app.application.quick_shift_service import QuickShiftService
from app.segment_repository import (
    QUICK_SHIFT_ORIGIN,
    SEGMENT_HEADERS,
    SEGMENT_ORIGIN_FIELD,
    ensure_segment_fields,
)


class QuickShiftServiceTests(unittest.TestCase):
    def test_create_builds_ad_hoc_segment_then_locked_shift(self) -> None:
        repository = object()
        created: dict[str, object] = {}
        shift_args: list[object] = []
        cancelled: list[str] = []

        def create_segment(repo: object, values: dict[str, object]) -> str:
            self.assertIs(repo, repository)
            created.update(values)
            return "SEG-2026-0001"

        def cancel_segment(repo: object, segment_id: str) -> None:
            self.assertIs(repo, repository)
            cancelled.append(segment_id)

        def create_shift(
            repo: object,
            segment_id: str,
            technician: str,
            day_value: object,
            hours_value: object,
            hors_horaire: bool,
            note: str,
        ) -> str:
            self.assertIs(repo, repository)
            shift_args.extend(
                [segment_id, technician, day_value, hours_value, hors_horaire, note]
            )
            return "MAN-001"

        service = QuickShiftService(
            repository,
            create_segment_record=create_segment,
            cancel_segment_record=cancel_segment,
            create_locked_shift_record=create_shift,
        )

        result = service.create(
            project_number="5094",
            project_name="Projet test",
            technician="Mathieu",
            day_value="2026-08-26",
            hours_value="7,5",
            hors_horaire=True,
            note="Intervention imprévue",
            description="Dépannage",
        )

        self.assertEqual(result.segment_id, "SEG-2026-0001")
        self.assertEqual(result.allocation_id, "MAN-001")
        self.assertEqual(created["NoDemande"], None)
        self.assertEqual(created["NumeroProjet"], "5094")
        self.assertEqual(created["NomProjet"], "Projet test")
        self.assertEqual(created["Technicien"], "Mathieu")
        self.assertEqual(created["DateDebut"], "2026-08-26")
        self.assertEqual(created["DateFin"], "2026-08-26")
        self.assertEqual(created["HeuresPrevues"], 7.5)
        self.assertEqual(created["TypePlanification"], "Fixe")
        self.assertEqual(created[SEGMENT_ORIGIN_FIELD], QUICK_SHIFT_ORIGIN)
        self.assertEqual(
            shift_args,
            ["SEG-2026-0001", "Mathieu", "2026-08-26", 7.5, True, "Intervention imprévue"],
        )
        self.assertEqual(cancelled, [])

    def test_create_cancels_generated_segment_when_shift_creation_fails(self) -> None:
        repository = object()
        cancelled: list[str] = []

        service = QuickShiftService(
            repository,
            create_segment_record=lambda _repo, _values: "SEG-FAIL",
            cancel_segment_record=lambda _repo, segment_id: cancelled.append(segment_id),
            create_locked_shift_record=lambda *_args: (_ for _ in ()).throw(
                ValueError("hors horaire requis")
            ),
        )

        with self.assertRaisesRegex(ValueError, "hors horaire requis"):
            service.create(
                project_number="5094",
                technician="Mathieu",
                day_value="2026-08-30",
                hours_value=8,
            )

        self.assertEqual(cancelled, ["SEG-FAIL"])

    def test_create_rejects_invalid_required_values_before_persistence(self) -> None:
        calls: list[str] = []
        service = QuickShiftService(
            object(),
            create_segment_record=lambda *_args: calls.append("segment") or "SEG-1",
            cancel_segment_record=lambda *_args: calls.append("cancel"),
            create_locked_shift_record=lambda *_args: calls.append("shift") or "MAN-1",
        )

        with self.assertRaises(ValueError):
            service.create(
                project_number="",
                technician="Mathieu",
                day_value="2026-08-26",
                hours_value=8,
            )
        with self.assertRaises(ValueError):
            service.create(
                project_number="5094",
                technician="",
                day_value="2026-08-26",
                hours_value=8,
            )
        with self.assertRaises(ValueError):
            service.create(
                project_number="5094",
                technician="Mathieu",
                day_value=None,
                hours_value=8,
            )
        with self.assertRaises(ValueError):
            service.create(
                project_number="5094",
                technician="Mathieu",
                day_value="2026-08-26",
                hours_value=0,
            )

        self.assertEqual(calls, [])


class SegmentFieldExtensionTests(unittest.TestCase):
    def test_optional_field_is_appended_without_reordering_existing_headers(self) -> None:
        original = list(SEGMENT_HEADERS)

        class FakeRepository:
            def __init__(self) -> None:
                self.headers: list[str] = []
                self.save_count = 0

            def _ensure_sheet_table(self, _sheet: str, headers: list[str], _table: str) -> None:
                self.headers = list(headers)

            def save(self) -> None:
                self.save_count += 1

        repo = FakeRepository()
        try:
            ensure_segment_fields(repo, [SEGMENT_ORIGIN_FIELD])  # type: ignore[arg-type]
            ensure_segment_fields(repo, [SEGMENT_ORIGIN_FIELD])  # type: ignore[arg-type]

            self.assertEqual(SEGMENT_HEADERS[:-1], original)
            self.assertEqual(SEGMENT_HEADERS[-1], SEGMENT_ORIGIN_FIELD)
            self.assertEqual(SEGMENT_HEADERS.count(SEGMENT_ORIGIN_FIELD), 1)
            self.assertEqual(repo.headers, SEGMENT_HEADERS)
        finally:
            SEGMENT_HEADERS[:] = original


if __name__ == "__main__":
    unittest.main()
