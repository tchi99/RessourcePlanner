from __future__ import annotations

from datetime import date
from pathlib import Path
import unittest

from app.application.commands import DemandApproveCommand, DemandUpdateCommand
from app.application.demand_service import DemandService
from app.application.errors import ApplicationError
from app.application.read_models import DemandReadModel


class _Demands:
    def __init__(self, *, record: DemandReadModel | None) -> None:
        self.record = record
        self.writes: list[tuple[object, ...]] = []

    def list(self):
        return (self.record,) if self.record is not None else ()

    def get(self, number: str):
        if self.record is not None and self.record.number == number:
            return self.record
        return None

    def create(self, values, *, submit=False):
        return "DMO-NEW"

    def update(self, number, updates, *, action, comment=""):
        self.writes.append((number, dict(updates), action, comment))


class _Planning:
    def rebuild(self):
        return {"allocated_hours": 8.0}


class _Sync:
    def sync_approved(self, _number: str):
        return None


def fictive_http_handler(service: DemandService, command: object) -> tuple[int, dict]:
    """Tiny transport adapter proving the application seam without importing FastAPI."""

    try:
        if isinstance(command, DemandUpdateCommand):
            return 200, {"reapproval_required": service.modify_command(command)}
        if isinstance(command, DemandApproveCommand):
            return 200, service.approve_command(command)
        raise AssertionError("unsupported test command")
    except ApplicationError as exc:
        status = 404 if exc.code.endswith("not_found") else 422
        return status, exc.as_dict()


class ApplicationHttpSeamTests(unittest.TestCase):
    def test_fictive_http_handler_calls_typed_service_without_excel_or_ui(self) -> None:
        demands = _Demands(
            record=DemandReadModel(
                number="DMO-1",
                status="Brouillon",
                desired_start=date(2026, 8, 25),
                desired_end=date(2026, 8, 29),
            )
        )
        service = DemandService(demands, _Planning(), _Sync())

        status, payload = fictive_http_handler(
            service,
            DemandUpdateCommand(
                number="DMO-1",
                description="Portée API",
            ),
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload, {"reapproval_required": False})
        self.assertEqual(demands.writes[0][1], {"Description": "Portée API"})

    def test_fictive_http_handler_translates_structured_not_found(self) -> None:
        service = DemandService(_Demands(record=None), _Planning(), _Sync())

        status, payload = fictive_http_handler(
            service,
            DemandUpdateCommand(number="DMO-MISSING", description="x"),
        )

        self.assertEqual(status, 404)
        self.assertEqual(payload["code"], "demand_not_found")
        self.assertEqual(payload["context"]["demand_number"], "DMO-MISSING")

    def test_http_seam_test_itself_does_not_need_fastapi_nicegui_or_excel(self) -> None:
        source = Path(__file__).read_text(encoding="utf-8")
        for forbidden_import in (
            "import fastapi",
            "from fastapi",
            "import nicegui",
            "from nicegui",
            "ExcelRepository",
            "xlwings",
        ):
            self.assertNotIn(forbidden_import, source)


if __name__ == "__main__":
    unittest.main()
