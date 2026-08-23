from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import unittest

from app.application.demand_service import DemandService
from app.application.runtime_services import demand_service


class DemandCreationServiceTests(unittest.TestCase):
    @staticmethod
    def _service(repository: object, create_record):
        return DemandService(
            repository,
            load_record=lambda _repo, _number: None,
            create_record=create_record,
            modify_record=lambda _repo, _number, _updates, _comment: None,
            submit_record=lambda _repo, _number: None,
            approve_record=lambda _repo, _number, _comment: None,
            request_correction_record=lambda _repo, _number, _comment: None,
            cancel_record=lambda _repo, _number: None,
            sync_approved_demand=lambda _repo, _number: None,
            rebuild_planning=lambda _repo: {},
        )

    def test_create_forwards_business_payload_and_submit_intent(self) -> None:
        repository = object()
        calls: list[object] = []

        def create_record(repo: object, values: object, submit: bool) -> str:
            self.assertIs(repo, repository)
            calls.append((values, submit))
            return "DMO-2026-0042"

        number = self._service(repository, create_record).create(
            {
                "NumeroProjet": "P-100",
                "DateDebutSouhaitee": "2026-08-24",
                "Description": "Travaux chantier",
            },
            submit=True,
        )

        self.assertEqual(number, "DMO-2026-0042")
        self.assertEqual(calls[0][1], True)
        self.assertEqual(calls[0][0]["NumeroProjet"], "P-100")
        self.assertEqual(calls[0][0]["Description"], "Travaux chantier")

    def test_create_strips_workflow_owned_fields(self) -> None:
        captured: dict[str, object] = {}

        def create_record(_repo: object, values: object, submit: bool) -> str:
            captured.update(values)
            captured["_submit"] = submit
            return "DMO-2026-0043"

        self._service(object(), create_record).create(
            {
                "NumeroProjet": "P-200",
                "DateDebutSouhaitee": "2026-08-25",
                "NoDemande": "FORGED",
                "Statut": "En planification",
                "ApprouvePar": "someone",
                "DateApprobation": "2026-08-01",
            },
            submit=False,
        )

        self.assertNotIn("NoDemande", captured)
        self.assertNotIn("Statut", captured)
        self.assertNotIn("ApprouvePar", captured)
        self.assertNotIn("DateApprobation", captured)
        self.assertEqual(captured["_submit"], False)

    def test_create_requires_project_and_start_date_before_storage(self) -> None:
        writes: list[str] = []

        def create_record(_repo: object, _values: object, _submit: bool) -> str:
            writes.append("write")
            return "DMO-2026-0044"

        service = self._service(object(), create_record)
        with self.assertRaisesRegex(ValueError, "projet"):
            service.create({"DateDebutSouhaitee": "2026-08-24"})
        with self.assertRaisesRegex(ValueError, "date de début"):
            service.create({"NumeroProjet": "P-300"})
        self.assertEqual(writes, [])

    def test_create_runs_in_repository_batch_when_available(self) -> None:
        events: list[object] = []

        @contextmanager
        def batch(_repo: object, label: str):
            events.append(("enter", label))
            try:
                yield
            finally:
                events.append(("exit", label))

        def create_record(_repo: object, _values: object, submit: bool) -> str:
            events.append(("create", submit))
            return "DMO-2026-0045"

        service = DemandService(
            object(),
            load_record=lambda _repo, _number: None,
            create_record=create_record,
            modify_record=lambda _repo, _number, _updates, _comment: None,
            submit_record=lambda _repo, _number: None,
            approve_record=lambda _repo, _number, _comment: None,
            request_correction_record=lambda _repo, _number, _comment: None,
            cancel_record=lambda _repo, _number: None,
            sync_approved_demand=lambda _repo, _number: None,
            rebuild_planning=lambda _repo: {},
            batch=batch,
        )
        service.create(
            {"NumeroProjet": "P-400", "DateDebutSouhaitee": "2026-08-24"}
        )

        self.assertEqual(
            events,
            [("enter", "create demand"), ("create", False), ("exit", "create demand")],
        )

    def test_runtime_adapter_uses_existing_repository_creation_semantics(self) -> None:
        calls: list[object] = []

        class FakeRepository:
            def create_demand(self, values: dict[str, object], submit: bool = False) -> str:
                calls.append((values, submit))
                return "DMO-2026-0046"

        number = demand_service(FakeRepository()).create(
            {
                "NumeroProjet": "P-500",
                "DateDebutSouhaitee": "2026-08-24",
                "Confirmation": "Tentative",
            },
            submit=True,
        )

        self.assertEqual(number, "DMO-2026-0046")
        self.assertEqual(calls[0][1], True)
        self.assertEqual(calls[0][0]["Confirmation"], "Tentative")

    def test_editor_creation_crosses_demand_service_boundary(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "app" / "demand_editor_ui.py").read_text(encoding="utf-8")

        self.assertIn("demand_service(self.repo).create(payload(), submit=False)", source)
        self.assertIn("demand_service(self.repo).create(payload(), submit=True)", source)
        self.assertNotIn("self.repo.create_demand(", source)


if __name__ == "__main__":
    unittest.main()
