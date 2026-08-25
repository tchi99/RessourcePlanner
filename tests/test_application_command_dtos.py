from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from datetime import date
from pathlib import Path
import unittest

from app.application.commands import (
    DemandCreateCommand,
    DemandUpdateCommand,
    ManualAllocationCreateCommand,
    QuickShiftCreateCommand,
    SegmentCreateCommand,
)
from app.application.errors import ApplicationError, ApplicationValidationError


ROOT = Path(__file__).resolve().parents[1]
APPLICATION = ROOT / "app" / "application"


class ApplicationCommandDtoTests(unittest.TestCase):
    def test_demand_create_normalizes_ui_mapping_to_typed_command(self) -> None:
        command = DemandCreateCommand.from_mapping(
            {
                "NumeroProjet": " P-100 ",
                "NomProjet": "Projet test",
                "DateDebutSouhaitee": "2026-08-26",
                "DateFinSouhaitee": "2026-08-28",
                "NombreRessources": "2",
                "TempsEstimeHeures": "15,5",
                "TempsEstimeJours": "2,5",
                "Confirmation": "Tentative",
            },
            submit=True,
        )

        self.assertEqual(command.project_number, "P-100")
        self.assertEqual(command.desired_start, date(2026, 8, 26))
        self.assertEqual(command.desired_end, date(2026, 8, 28))
        self.assertEqual(command.resource_count, 2)
        self.assertEqual(command.estimated_hours, 15.5)
        self.assertEqual(command.estimated_days, 2.5)
        self.assertTrue(command.submit)
        self.assertEqual(command.confirmation, "Tentative")

        values = command.to_repository_values()
        self.assertEqual(values["NumeroProjet"], "P-100")
        self.assertEqual(values["DateDebutSouhaitee"], date(2026, 8, 26))
        self.assertEqual(values["NombreRessources"], 2)

    def test_demand_update_is_a_closed_patch_contract(self) -> None:
        command = DemandUpdateCommand.from_mapping(
            "DMO-1",
            {
                "Description": "Nouvelle portée",
                "DateDebutSouhaitee": "2026-08-27",
            },
        )

        self.assertEqual(
            command.to_repository_values(),
            {
                "DateDebutSouhaitee": date(2026, 8, 27),
                "Description": "Nouvelle portée",
            },
        )

        with self.assertRaises(ApplicationValidationError) as raised:
            DemandUpdateCommand.from_mapping("DMO-1", {"Statut": "Annulée"})

        self.assertEqual(raised.exception.code, "demand_update_fields_invalid")
        self.assertEqual(raised.exception.context["fields"], ["Statut"])

    def test_segment_command_normalizes_storage_payload_without_excel_dependency(self) -> None:
        command = SegmentCreateCommand.from_mapping(
            {
                "NoDemande": "DMO-2",
                "NumeroProjet": "5094",
                "DateDebut": "2026-08-26",
                "DateFin": "2026-08-27",
                "HeuresPrevues": "7,5",
                "CompetenceRequise": "Programmation",
                "HorsHoraireAutorise": "Oui",
            }
        )

        self.assertEqual(command.start_date, date(2026, 8, 26))
        self.assertEqual(command.planned_hours, 7.5)
        self.assertTrue(command.outside_standard_hours)
        self.assertEqual(command.to_repository_values()["HorsHoraireAutorise"], "Oui")

    def test_invalid_date_window_is_structured_validation_error(self) -> None:
        with self.assertRaises(ApplicationValidationError) as raised:
            DemandCreateCommand.from_mapping(
                {
                    "NumeroProjet": "P-1",
                    "DateDebutSouhaitee": "2026-08-28",
                    "DateFinSouhaitee": "2026-08-27",
                }
            )

        self.assertEqual(raised.exception.code, "demand_date_window_invalid")
        self.assertEqual(raised.exception.context["start"], "2026-08-28")

    def test_allocation_and_quick_shift_commands_normalize_date_and_hours(self) -> None:
        allocation = ManualAllocationCreateCommand.from_values(
            "SEG-1",
            " Alice ",
            "2026-08-26",
            "4,5",
            True,
            " chantier ",
        )
        quick = QuickShiftCreateCommand.from_values(
            project_number=" 5094 ",
            project_name="Projet",
            technician=" Bob ",
            day_value="2026-08-27",
            hours_value="6,25",
        )

        self.assertEqual(allocation.technician, "Alice")
        self.assertEqual(allocation.day, date(2026, 8, 26))
        self.assertEqual(allocation.hours, 4.5)
        self.assertEqual(quick.project_number, "5094")
        self.assertEqual(quick.technician, "Bob")
        self.assertEqual(quick.hours, 6.25)

    def test_commands_are_immutable(self) -> None:
        command = QuickShiftCreateCommand.from_values(
            project_number="P-1",
            technician="Alice",
            day_value="2026-08-26",
            hours_value=8,
        )
        with self.assertRaises(FrozenInstanceError):
            command.hours = 4  # type: ignore[misc]

    def test_application_error_has_transport_neutral_payload(self) -> None:
        error = ApplicationError(
            "Impossible de planifier",
            code="planning_unavailable",
            context={"segment_id": "SEG-1"},
        )

        self.assertEqual(
            error.as_dict(),
            {
                "code": "planning_unavailable",
                "message": "Impossible de planifier",
                "context": {"segment_id": "SEG-1"},
            },
        )
        self.assertEqual(str(error), "Impossible de planifier")

    def test_command_and_error_modules_are_transport_and_storage_neutral(self) -> None:
        forbidden = (
            "nicegui",
            "fastapi",
            "pydantic",
            "sqlalchemy",
            "xlwings",
            "excel_repository",
            "app.v13",
            "app.v14",
            "app.v15",
            "app.v16",
            "app.v17",
            "app.v18",
        )
        files = [
            APPLICATION / "errors.py",
            *(APPLICATION / "commands").glob("*.py"),
        ]
        for path in files:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imports: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.append(node.module or "")
            for module in imports:
                self.assertFalse(
                    any(token in module for token in forbidden),
                    f"{path.name} leaks transport/storage dependency: {module}",
                )


if __name__ == "__main__":
    unittest.main()
