from __future__ import annotations

import unittest
from datetime import date

from app.domain.communication_source import (
    technician_ids_for_weekly_communication,
    weekly_assignments_from_records,
)


WEEK = date(2026, 8, 24)


class CommunicationSourceTests(unittest.TestCase):
    def test_builds_assignment_with_manager_from_demand(self) -> None:
        rows = weekly_assignments_from_records(
            [
                {
                    "IDSegment": "S-1",
                    "NoDemande": "D-1",
                    "Technicien": "tech-a",
                    "Date": "2026-08-24",
                    "Heures": 8,
                    "TypeAllocation": "Flexible",
                    "HorsHoraire": "Non",
                }
            ],
            [{"IDSegment": "S-1", "Statut": "Planifié", "NumeroProjet": "P-1", "NomProjet": "Projet démo"}],
            [{"NoDemande": "D-1", "ChargeProjet": "pm-a"}],
            WEEK,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].resource_id, "tech-a")
        self.assertEqual(rows[0].project_manager_id, "pm-a")
        self.assertEqual(rows[0].project_number, "P-1")

    def test_excludes_missing_outside_schedule_placeholder(self) -> None:
        rows = weekly_assignments_from_records(
            [
                {
                    "IDSegment": "S-1",
                    "Technicien": "tech-a",
                    "Date": "2026-08-24",
                    "Heures": 8,
                    "TypeAllocation": "Flexible",
                    "HorsHoraire": "Requis",
                }
            ],
            [{"IDSegment": "S-1", "Statut": "Planifié"}],
            [],
            WEEK,
        )
        self.assertEqual(rows, [])

    def test_excludes_rows_outside_selected_week_and_cancelled_segments(self) -> None:
        rows = weekly_assignments_from_records(
            [
                {"IDSegment": "outside", "Technicien": "tech-a", "Date": "2026-08-31", "Heures": 8},
                {"IDSegment": "cancelled", "Technicien": "tech-a", "Date": "2026-08-25", "Heures": 8},
            ],
            [
                {"IDSegment": "outside", "Statut": "Planifié"},
                {"IDSegment": "cancelled", "Statut": "Annulé"},
            ],
            [],
            WEEK,
        )
        self.assertEqual(rows, [])

    def test_aggregates_multiple_rows_for_same_assignment(self) -> None:
        rows = weekly_assignments_from_records(
            [
                {
                    "IDSegment": "S-1",
                    "Technicien": "tech-a",
                    "Date": "2026-08-24",
                    "Heures": 3,
                    "TypeAllocation": "Flexible",
                },
                {
                    "IDSegment": "S-1",
                    "Technicien": "tech-a",
                    "Date": "2026-08-24",
                    "Heures": 5,
                    "TypeAllocation": "Locked",
                },
            ],
            [{"IDSegment": "S-1", "Statut": "Planifié"}],
            [],
            WEEK,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].hours, 8.0)
        self.assertEqual(rows[0].allocation_type, "Planifié")

    def test_outside_schedule_is_preserved_for_real_allocation(self) -> None:
        rows = weekly_assignments_from_records(
            [
                {
                    "IDSegment": "S-1",
                    "Technicien": "tech-a",
                    "Date": "2026-08-24",
                    "Heures": 4,
                    "HorsHoraire": "Oui",
                }
            ],
            [{"IDSegment": "S-1", "Statut": "Planifié"}],
            [],
            WEEK,
        )
        self.assertTrue(rows[0].outside_schedule)

    def test_explicit_technician_audience_is_deduplicated(self) -> None:
        techs = technician_ids_for_weekly_communication(
            [{"name": "tech-b"}, {"name": "tech-a"}, {"name": "tech-a"}, {"name": ""}]
        )
        self.assertEqual(techs, ["tech-a", "tech-b"])


if __name__ == "__main__":
    unittest.main()
